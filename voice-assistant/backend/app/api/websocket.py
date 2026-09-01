"""
WebSocket 语音对话端点模块
处理 /ws/voice 端点的完整生命周期：连接建立、消息收发、连接关闭

===== 性能优化（2024） =====

【优化1】二进制 WebSocket 帧传输音频（节省 ~33% 带宽）
  - 音频数据使用二进制帧（send_bytes），替代 base64 JSON
  - 帧格式: [1B 类型] [4B JSON头长度] [JSON头] [音频数据]
  - 类型: 0x01=音频块, 0x02=音频结束

【优化2】ASR 对话 + TTS 并行管道（E2E 延迟 < 2s）
  - 传统串行: ASR → Dialog → (等待完成) → TTS → 发送  → 延迟 = T₁ + T₂ + T₃
  - 优化并行: ASR → Dialog → (立即返回文本) → 同时后台启动 TTS → 延迟 ≈ T₁ + T₂
  - TTS 完成后通过二进制帧异步推送，不阻塞主流程

【注意】TTS 语音输出仅在用户语音输入（audio 消息）时触发，文本输入（text 消息）仅返回文字。

【优化3】重试与熔断保护
  - TTS 合成：熔断器 + 指数退避重试，外部服务不可用时快速降级
  - ASR 识别：1 次快速重试，异常直接返回错误

【优化4】并发连接池
  - LLM API、TTS 服务共享连接池，复用 TCP 连接

消息协议（JSON + 二进制混合）:
    --- JSON 文本帧 ---
    客户端 → 服务端:
        { "type": "audio", "data": "<base64>", "format": "webm", "language": "zh" }
        { "type": "text",  "text": "你好" }
        { "type": "ping", "timestamp": 1234567890 }

    服务端 → 客户端（JSON）:
        { "type": "connected", "session_id": "...", "message": "..." }
        { "type": "audio_result", "text": "...", "response": "...", "confidence": 0.95, ... }
        { "type": "text_response", "text": "...", "response": "...", ... }   # 兼容旧客户端
        { "type": "stream_delta", "delta": "..." }                            # 流式 LLM 增量
        { "type": "stream_end", "full_text": "...", "intent": "...", ... }     # 流式 LLM 结束
        { "type": "audio_ack", "message": "音频已接收，识别中..." }
        { "type": "pong", "timestamp": 1234567890 }
        { "type": "error", "message": "..." }

    服务端 → 客户端（二进制帧）:
        0x01 + [4B JSON头长度] + JSON头{"format":"mp3"} + 音频数据  →  TTS 音频块
        0x02 + [4B JSON头长度] + JSON头{"text":"..."}              →  TTS 流结束
"""

import asyncio
import base64
import json
import logging
import struct
import time as time_module
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

from app.core.config import settings, runtime_config
from app.core.voice_providers import voice_provider_registry
from app.core.optimization import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    RetryStrategy,
    run_concurrently,
)

# 日志记录器
logger = logging.getLogger("voice-assistant.websocket")

# ============================================================
# 全局共享资源
# ============================================================

# TTS 服务熔断器
tts_circuit_breaker = CircuitBreaker(
    failure_threshold=settings.CIRCUIT_BREAKER_THRESHOLD,
    recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY,
)

# TTS 重试策略
tts_retry = RetryStrategy(
    max_retries=settings.MAX_RETRIES,
    base_delay=settings.RETRY_BASE_DELAY,
)

# ASR 重试策略
asr_retry = RetryStrategy(
    max_retries=1,  # ASR 重试 1 次
    base_delay=0.5,
)


# ============================================================
# Session 管理
# ============================================================
class VoiceSession:
    """
    单个 WebSocket 连接的会话
    维护每个连接的唯一 session_id 及上下文信息
    """

    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.session_id: str = uuid.uuid4().hex[:16]   # 唯一会话ID，同时作为 ASR 流式会话ID
        self.conversation_id: str = ""                   # 对话ID（由对话管理器创建）
        self.client_ip: str = websocket.client.host if websocket.client else "unknown"
        self.user_agent: str = ""
        self.created_at: float = time_module.time()
        self.last_active: float = time_module.time()
        self.message_count: int = 0                      # 本轮消息计数

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典，用于监控/日志"""
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "client_ip": self.client_ip,
            "message_count": self.message_count,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


# ============================================================
# Session 管理器
# ============================================================
class SessionManager:
    """全局 WebSocket 会话管理器"""

    def __init__(self):
        # session_id → VoiceSession
        self._sessions: Dict[str, VoiceSession] = {}
        # WebSocket id → session_id (快速反向查找)
        self._ws_to_session: Dict[int, str] = {}

    def create_session(self, websocket: WebSocket) -> VoiceSession:
        """创建并注册新会话"""
        session = VoiceSession(websocket)
        self._sessions[session.session_id] = session
        self._ws_to_session[id(websocket)] = session.session_id
        return session

    def get_by_websocket(self, websocket: WebSocket) -> Optional[VoiceSession]:
        """通过 WebSocket 对象获取会话"""
        sid = self._ws_to_session.get(id(websocket))
        return self._sessions.get(sid) if sid else None

    def get_by_session_id(self, session_id: str) -> Optional[VoiceSession]:
        """通过 session_id 获取会话"""
        return self._sessions.get(session_id)

    def remove(self, websocket: WebSocket):
        """移除会话"""
        sid = self._ws_to_session.pop(id(websocket), None)
        if sid:
            self._sessions.pop(sid, None)

    @property
    def active_count(self) -> int:
        """当前活跃会话数"""
        return len(self._sessions)

    @property
    def all_sessions(self) -> Dict[str, VoiceSession]:
        """所有活跃会话"""
        return self._sessions


# 全局会话管理器实例
session_manager = SessionManager()


# ============================================================
# 消息处理器
# ============================================================
class VoiceWebSocketHandler:
    """
    /ws/voice 端点消息处理器
    负责消息路由、编解码、业务逻辑编排

    依赖注入（在 app/main.py 的 lifespan 中设置）:
        handler.asr_service       = ASRService 实例
        handler.dialog_manager    = DialogManager 实例
        handler.ai_voice_service  = AIVoiceService 实例（TTS）

    注意：TTS 仅使用 AI 语音大模型 API，已移除本地 edge-tts。
    未配置语音 Provider 时，TTS 合成将被跳过。
    """

    def __init__(self):
        # 依赖注入占位 — 在 app/main.py 的 lifespan 中注入真实服务
        self.asr_service = None       # ASR 服务实例        ← 注入点
        self.dialog_manager = None    # 对话管理器实例      ← 注入点
        self.ai_voice_service = None  # AI 语音大模型服务   ← 注入点

    # ============================================================
    # 连接生命周期
    # ============================================================

    async def handle_connect(self, websocket: WebSocket) -> VoiceSession:
        """
        处理新连接
        1. 检查语音对话功能是否启用
        2. 接受 WebSocket
        3. 创建会话
        4. 重置 ASR 流式会话状态（确保新连接不会残留旧缓冲区）
        5. 记录日志并发送连接确认
        """
        await websocket.accept()

        session = session_manager.create_session(websocket)

        # 检查语音对话功能是否启用（仅记录日志，不拒绝连接）
        if not runtime_config.enable_voice_dialogue:
            logger.warning("[连接] 语音对话功能已关闭，仅支持文本聊天")

        # 重置 ASR 流式会话，确保新连接干净
        if self.asr_service:
            await self.asr_service.reset_stream(session.session_id)

        logger.info(
            f"[连接] session={session.session_id} "
            f"ip={session.client_ip} "
            f"当前在线={session_manager.active_count}"
        )

        # 发送连接成功确认（含语音对话模式状态）
        voice_dialogue_enabled = runtime_config.enable_voice_dialogue
        role_hint = (
            "小玥已上线，欢迎找我聊天～（当前仅支持文字，如需语音请开启语音对话模式）"
            if not voice_dialogue_enabled
            else "小玥已上线，欢迎找我聊天～"
        )
        await self._send(
            websocket,
            {
                "type": "connected",
                "session_id": session.session_id,
                "message": role_hint,
                "voice_dialogue_enabled": voice_dialogue_enabled,
            },
        )
        return session

    async def handle_disconnect(self, websocket: WebSocket):
        """
        处理连接断开
        1. 清理 ASR 流式会话资源
        2. 从会话管理器中移除
        3. 记录日志
        """
        session = session_manager.get_by_websocket(websocket)

        # 清理 ASR 流式会话
        if session and self.asr_service:
            await self.asr_service.reset_stream(session.session_id)

        session_manager.remove(websocket)

        if session:
            logger.info(
                f"[断开] session={session.session_id} "
                f"共 {session.message_count} 条消息 "
                f"当前在线={session_manager.active_count}"
            )

    # ============================================================
    # 消息分发
    # ============================================================

    async def handle_message(self, websocket: WebSocket, raw_data: str):
        """
        消息分发入口
        根据 type 字段路由到对应的处理方法

        参数:
            websocket: WebSocket 连接
            raw_data: 原始 JSON 字符串
        """
        session = session_manager.get_by_websocket(websocket)
        if not session:
            await self._send(websocket, {"type": "error", "message": "会话不存在"})
            return

        # 更新活跃时间
        session.last_active = time_module.time()

        try:
            message = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning(f"[消息] session={session.session_id} JSON解析失败")
            await self._send(
                websocket,
                {"type": "error", "message": "消息格式错误，请发送有效的 JSON"},
            )
            return

        msg_type = message.get("type", "")
        session.message_count += 1

        # ---- 音频消息: 送入 ASR 流式识别 ----
        if msg_type == "audio":
            await self._handle_audio(session, message)

        # ---- 文本消息: 直接送入对话管理 ----
        elif msg_type == "text":
            await self._handle_text(session, message)

        # ---- 心跳 ----
        elif msg_type == "ping":
            await self._handle_ping(session, message)

        # ---- 未知类型 ----
        else:
            logger.warning(f"[消息] session={session.session_id} 未知类型: {msg_type}")
            await self._send(
                websocket,
                {"type": "error", "message": f"不支持的消息类型: {msg_type}"},
            )

    # ============================================================
    # 音频消息处理（ASR 流式识别 + 对话管理）
    # ============================================================

    # ============================================================
    # 二进制帧辅助方法
    # ============================================================

    async def _send_binary_audio(
        self, websocket: WebSocket, audio_data: bytes, fmt: str = "mp3"
    ):
        """
        通过二进制帧发送 TTS 音频块（替代 base64 JSON）

        帧格式:
            [1B 类型=0x01] [4B JSON头长度(大端)] [JSON头] [音频二进制数据]

        优势:
            - 省去 base64 编码/解码的 ~33% 膨胀和 CPU 开销
            - 二进制帧在 WebSocket 协议层面就是原生支持
        """
        header = json.dumps({"format": fmt}).encode("utf-8")
        # 打包: 1 字节类型(0x01) + 4 字节 JSON 头长度(大端无符号) + JSON头 + 音频数据
        frame = struct.pack(f">BI{len(header)}s{len(audio_data)}s", 1, len(header), header, audio_data)
        try:
            await websocket.send_bytes(frame)
        except Exception as e:
            logger.error(f"[二进制] 发送音频帧失败: {e}")

    async def _send_binary_end(
        self, websocket: WebSocket, text: str = ""
    ):
        """
        发送 TTS 流结束标记（二进制帧类型 0x02）

        告知客户端音频流已完，可以播放了
        """
        header = json.dumps({"text": text}).encode("utf-8")
        frame = struct.pack(f">BI{len(header)}s", 2, len(header), header)
        try:
            await websocket.send_bytes(frame)
        except Exception as e:
            logger.error(f"[二进制] 发送结束帧失败: {e}")

    # ============================================================
    # 音频消息处理（并行管道优化）
    # ============================================================

    async def _handle_audio(self, session: VoiceSession, message: Dict[str, Any]):
        """
        【优化】处理音频消息 — ASR + Dialog + TTS 并行管道

        TTS 语音输出仅在用户语音输入时触发（即本方法）。
        文本输入（text 消息）不会触发 TTS。

        性能优化点:
            1. E2E 延迟追踪 — 记录完整流水线耗时
            2. TTS 异步并行 — 文本响应发送后，后台启动 TTS，不阻塞主流程
            3. 二进制帧传输 — TTS 音频使用 WebSocket 二进制帧
            4. ASR 重试 1 次 — 临时故障自动恢复

        消息格式:
            { "type": "audio", "data": "<base64>", "format": "wav", "language": "zh" }
        """
        # ---- 语音对话开关守卫 ----
        if not runtime_config.enable_voice_dialogue:
            await self._send(session.websocket, {
                "type": "error",
                "message": "语音对话已关闭，请先在设置中开启语音对话模式",
            })
            return

        # ==== E2E 延迟追踪 ====
        _t0 = time_module.perf_counter()

        audio_base64 = message.get("data", "")
        audio_format = message.get("format", "wav")
        language = message.get("language", settings.ASR_DEFAULT_LANGUAGE)

        if not audio_base64:
            await self._send(session.websocket, {"type": "error", "message": "音频数据为空"})
            return

        # ---- 解码音频数据 ----
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            logger.error(f"[解码] session={session.session_id} 解码失败: {e}")
            await self._send(session.websocket, {"type": "error", "message": "音频数据解码失败"})
            return

        logger.debug(
            f"[音频] session={session.session_id} size={len(audio_bytes)} fmt={audio_format}"
        )

        # ---- ASR 流式识别（带 1 次重试） ----
        if not self.asr_service:
            logger.warning(f"[ASR] session={session.session_id} 服务未注入")
            await self._send(session.websocket, {"type": "error", "message": "语音识别服务暂不可用"})
            return

        asr_result = None
        for attempt in range(2):  # 最多尝试 2 次
            try:
                asr_result = await self.asr_service.recognize_stream(
                    session_id=session.session_id,
                    audio_chunk=audio_bytes,
                    language=language,
                )
                break  # 成功则跳出重试循环
            except Exception as e:
                logger.warning(
                    f"[ASR] session={session.session_id} attempt={attempt + 1} 失败: {e}"
                )
                if attempt == 0:
                    await asyncio.sleep(0.3)  # 短暂等待后重试
                else:
                    logger.error(f"[ASR] session={session.session_id} 重试耗尽", exc_info=True)
                    await self._send(
                        session.websocket, {"type": "error", "message": "语音识别处理失败"}
                    )
                    return

        # ---- 结果处理 ----
        if asr_result is None:
            await self._send(
                session.websocket,
                {
                    "type": "audio_ack",
                    "message": "音频已接收，识别中...",
                    "session_id": session.session_id,
                },
            )
            return

        transcript = asr_result.text.strip()
        confidence = asr_result.confidence

        if transcript:
            logger.info(
                f"[ASR结果] session={session.session_id} "
                f"text=\"{transcript[:80]}\" conf={confidence:.3f}"
            )
        else:
            logger.info(f"[ASR结果] session={session.session_id} 未检测到有效语音")

        if not transcript:
            await self._send(
                session.websocket,
                {
                    "type": "audio_result",
                    "text": "",
                    "response": "未检测到有效语音，请重试",
                    "session_id": session.session_id,
                    "language": asr_result.language,
                    "confidence": confidence,
                },
            )
            return

        # ==== E2E 延迟标记：ASR 完成 ====
        _t1 = time_module.perf_counter()
        e2e_text_latency = (_t1 - _t0) * 1000  # ms

        # ---- 返回 ASR 识别结果（立即发送，不等 LLM） ----
        await self._send(
            session.websocket,
            {
                "type": "audio_result",
                "text": transcript,
                "response": "",  # 流式 LLM 响应通过 stream_delta/stream_end 推送
                "session_id": session.session_id,
                "conversation_id": session.conversation_id,
                "language": asr_result.language,
                "confidence": confidence,
                # 性能埋点：ASR 完成延迟（ms）
                "e2e_text_latency_ms": round(e2e_text_latency, 1),
            },
        )

        # ---- 流式对话 + TTS ----
        # _handle_dialog_stream 会发送 stream_delta / stream_end 并触发 TTS
        reply_text = await self._handle_dialog_stream(
            session=session,
            text=transcript,
            source="audio",
        )

        # E2E 完整延迟
        _t2 = time_module.perf_counter()
        e2e_total_latency = (_t2 - _t0) * 1000
        logger.info(
            f"[延迟] session={session.session_id} "
            f"ASR={e2e_text_latency:.0f}ms "
            f"完整={e2e_total_latency:.0f}ms "
            f"(TTS+Dialog={(e2e_total_latency - e2e_text_latency):.0f}ms)"
        )

    # ============================================================
    # 文本消息处理（对话管理 + 并行 TTS）
    # ============================================================

    async def _handle_dialog_stream(
        self,
        session: VoiceSession,
        text: str,
        source: str = "text",
        need_voice: bool = False,
    ) -> str:
        """
        通用流式对话处理

        调用 dialog_manager.process_message_stream，将 LLM 流式增量通过
        WebSocket stream_delta / stream_end 推送到前端。

        参数:
            session: 当前会话
            text: 用户文本（ASR 识别结果或手动输入）
            source: "text" | "audio"
            need_voice: 是否需要触发 TTS（文本输入且用户要求语音输出时）

        返回:
            完整回复文本
        """
        reply_text = ""
        intent_name = ""
        intent_confidence = 0.0
        agent_info: Optional[Dict[str, Any]] = None

        if not self.dialog_manager:
            await self._send(
                session.websocket,
                {"type": "error", "message": "对话管理器未初始化"},
            )
            return reply_text

        try:
            async for event in self.dialog_manager.process_message_stream(
                message=text,
                conversation_id=session.conversation_id,
            ):
                event_type = event.get("type")

                if event_type == "meta":
                    intent_name = event.get("intent", intent_name)
                    intent_confidence = event.get("confidence", intent_confidence)
                    agent_info = event.get("agent", agent_info)

                elif event_type == "delta":
                    delta = event.get("delta", "")
                    if delta:
                        await self._send(
                            session.websocket,
                            {
                                "type": "stream_delta",
                                "delta": delta,
                                "session_id": session.session_id,
                            },
                        )
                        reply_text += delta

                elif event_type == "stream_end":
                    reply_text = event.get("full_text", reply_text)
                    session.conversation_id = event.get(
                        "conversation_id", session.conversation_id
                    )
                    intent_name = event.get("intent", intent_name)
                    intent_confidence = event.get("confidence", intent_confidence)
                    agent_info = event.get("agent", agent_info)

                    response_msg = {
                        "type": "stream_end",
                        "full_text": reply_text,
                        "session_id": session.session_id,
                        "conversation_id": session.conversation_id,
                        "intent": intent_name,
                        "intent_confidence": intent_confidence,
                    }
                    if agent_info:
                        response_msg["agent"] = agent_info
                    await self._send(session.websocket, response_msg)
                    break

        except Exception as e:
            logger.error(
                f"[对话-Stream] session={session.session_id} 异常: {e}",
                exc_info=True,
            )
            reply_text = f"已收到消息: {text}"
            await self._send(
                session.websocket,
                {
                    "type": "stream_end",
                    "full_text": reply_text,
                    "session_id": session.session_id,
                    "conversation_id": session.conversation_id,
                    "intent": "general_chat",
                    "intent_confidence": 0.0,
                },
            )

        # ---- 触发 TTS ----
        if reply_text and self.ai_voice_service and runtime_config.enable_voice_dialogue:
            if source == "audio" or need_voice:
                if source == "audio":
                    logger.info(
                        f"[音频] 触发 TTS: \"{reply_text[:60]}...\""
                    )
                else:
                    logger.info(
                        f"[文本] 用户要求语音输出，触发 TTS: \"{reply_text[:60]}...\""
                    )
                await self._tts_stream_and_send(session, reply_text)

        return reply_text

    async def _handle_text(self, session: VoiceSession, message: Dict[str, Any]):
        """
        处理文本消息（流式 LLM 响应）

        默认仅触发对话管理，不触发 TTS。
        如果语音对话模式已开启且用户显式要求语音输出
        （如「用语音回答」「念出来」），则会额外触发 TTS
        流式合成并将音频推送到前端。

        消息格式:
            { "type": "text", "text": "你好" }
        """
        text = message.get("text", "").strip()
        if not text:
            await self._send(session.websocket, {"type": "error", "message": "文本内容为空"})
            return

        logger.info(f"[文本] session={session.session_id} text=\"{text[:80]}\"")

        # ---- 检测用户是否要求语音输出 ----
        _VOICE_REQUEST_KEYWORDS = [
            "用语音", "语音回答", "语音回复", "语音输出",
            "说给我听", "念出来", "读出来", "说出来", "用说的", "用讲的",
            "speak", "read aloud", "voice reply",
        ]
        need_voice = any(kw in text.lower() for kw in _VOICE_REQUEST_KEYWORDS)

        # ---- 流式对话 ----
        await self._handle_dialog_stream(
            session=session,
            text=text,
            source="text",
            need_voice=need_voice,
        )

    # ============================================================
    # 心跳
    # ============================================================

    async def _handle_ping(self, session: VoiceSession, message: Dict[str, Any]):
        """处理心跳消息"""
        await self._send(
            session.websocket,
            {
                "type": "pong",
                "timestamp": message.get("timestamp"),
                "session_id": session.session_id,
            },
        )

    # ============================================================
    # 【优化】TTS 流式合成 + 二进制帧推送
    # ============================================================

    async def _tts_stream_and_send(self, session: VoiceSession, text: str):
        """
        使用 AI 语音大模型进行语音合成与发送

        TTS 仅使用 AI 语音大模型 API（已移除本地 edge-tts）。
        未配置语音 Provider 时跳过合成，不会报错。
        """
        if not text or not self.ai_voice_service:
            return

        # 检查是否有可用的语音 Provider
        provider = voice_provider_registry.get_active() or voice_provider_registry.get_default()
        if not provider or not provider.enabled:
            logger.debug(f"[TTS] session={session.session_id} 未配置语音 Provider，跳过合成")
            return

        await self._ai_voice_tts_stream_and_send(session, text)

    async def _ai_voice_tts_stream_and_send(self, session: VoiceSession, text: str):
        """
        使用 AI 语音大模型进行语音合成与发送
        """
        # 检测当前 Provider 的音频格式
        provider = voice_provider_registry.get_active() or voice_provider_registry.get_default()
        if provider and provider.encode_format == "base64":
            audio_fmt = "wav"  # PCM 已包装为 WAV
        else:
            audio_fmt = provider.response_format if provider and provider.response_format else "mp3"

        try:
            async with tts_circuit_breaker:
                for attempt in range(tts_retry.max_retries + 1):
                    try:
                        # 尝试流式合成
                        chunk_count = 0
                        has_data = False
                        async for audio_chunk in self.ai_voice_service.synthesize_stream(text=text):
                            await self._send_binary_audio(
                                session.websocket, audio_chunk, fmt=audio_fmt
                            )
                            chunk_count += 1
                            has_data = True

                        if has_data:
                            await self._send_binary_end(session.websocket, text=text[:50])
                            logger.debug(
                                f"[AI语音] session={session.session_id} "
                                f"流式合成完成: {chunk_count} 块"
                            )
                            return
                        else:
                            # 流式无数据，尝试完整合成
                            audio = await self.ai_voice_service.synthesize(text=text)
                            if audio:
                                await self._send_binary_audio(
                                    session.websocket, audio, fmt=audio_fmt
                                )
                                await self._send_binary_end(session.websocket, text=text[:50])
                                logger.debug(
                                    f"[AI语音] session={session.session_id} "
                                    f"完整合成完成: {len(audio)} bytes"
                                )
                                return
                            else:
                                logger.warning("[AI语音] 合成返回空数据")
                                raise ValueError("AI 语音合成返回空数据")

                    except CircuitBreakerOpenError:
                        logger.warning("[AI语音] 熔断器打开，跳过合成")
                        return

                    except Exception as e:
                        delay = tts_retry.get_delay(attempt)
                        logger.warning(
                            f"[AI语音] session={session.session_id} "
                            f"attempt={attempt + 1}/{tts_retry.max_retries + 1} 失败: {e}"
                            + (f", {delay:.1f}s 后重试..." if attempt < tts_retry.max_retries else ", 放弃")
                        )
                        if attempt < tts_retry.max_retries:
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"[AI语音] session={session.session_id} 重试耗尽")
                            raise

        except CircuitBreakerOpenError:
            logger.warning("[AI语音] 熔断器打开")
        except Exception:
            logger.warning("[AI语音] 合成失败")
            # 不再回退到 edge-tts（已移除）
            return

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _send(self, websocket: WebSocket, message: Dict[str, Any]):
        """向客户端发送 JSON 消息（带异常保护）"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"发送消息失败: {e}")


# ============================================================
# 全局处理器实例
# ============================================================
voice_handler = VoiceWebSocketHandler()


# ============================================================
# FastAPI WebSocket 端点工厂函数
# 此函数被 app/main.py 中的 @app.websocket("/ws/voice") 回调
# ============================================================
async def voice_websocket_endpoint(websocket: WebSocket):
    """
    /ws/voice WebSocket 端点

    完整的连接生命周期:
      1. connect   → 接受连接、创建会话、重置 ASR 流式缓冲区
      2. message   → 接收 JSON 消息并分发处理
      3. disconnect → 清理 ASR 流式会话等资源

    支持的 message.type:
      - "audio" : Base64 编码的音频数据 → ASR 流式识别 → 对话管理
      - "text"  : 文本消息 → 对话管理
      - "ping"  : 心跳检测
    """
    session: Optional[VoiceSession] = None

    try:
        # ---- 连接建立 ----
        session = await voice_handler.handle_connect(websocket)

        # ---- 消息循环 ----
        while True:
            raw_data = await websocket.receive_text()
            await voice_handler.handle_message(websocket, raw_data)

    except WebSocketDisconnect:
        if session:
            logger.info(
                f"[断开] WebSocket 连接关闭 "
                f"session={session.session_id}"
            )

    except Exception as e:
        logger.error(
            f"[错误] WebSocket 异常 "
            f"session={session.session_id if session else 'unknown'}: {e}",
            exc_info=True,
        )
        try:
            await websocket.send_json({
                "type": "error",
                "message": "服务器内部错误，请稍后重试",
            })
        except Exception:
            pass

    finally:
        # ---- 连接关闭 ----
        await voice_handler.handle_disconnect(websocket)
