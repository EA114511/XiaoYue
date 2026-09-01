"""
WebSocket 连接和音频传输测试

测试覆盖:
  - VoiceWebSocketHandler.handle_connect() — 连接建立与会话创建
  - VoiceWebSocketHandler.handle_disconnect() — 连接断开与会话清理
  - VoiceWebSocketHandler.handle_message() — 消息分发路由
  - _handle_audio() — 音频消息处理（ASR + 对话 + TTS 完整链路）
  - _handle_text() — 文本消息处理
  - _handle_ping() — 心跳检测
  - SessionManager — 会话管理
  - 错误处理 — 无效 JSON、空音频、ASR 异常
  - _maybe_tts() — TTS 合成发送
"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import WebSocket, WebSocketDisconnect

from app.api.websocket import (
    VoiceWebSocketHandler,
    VoiceSession,
    SessionManager,
    session_manager,
    voice_handler,
)


# ============================================================
# 流式响应辅助
# ============================================================

def mock_stream_result(
    response: str,
    intent: str,
    confidence: float = 0.80,
    entities: dict = None,
    conversation_id: str = "conv_1",
    agent: dict = None,
):
    """构造一个模拟的 DialogManager.process_message_stream 异步生成器"""
    async def _gen():
        yield {
            "type": "meta",
            "intent": intent,
            "confidence": confidence,
            "entities": entities or {},
            "agent": agent,
        }
        yield {"type": "delta", "delta": response}
        yield {
            "type": "stream_end",
            "full_text": response,
            "intent": intent,
            "confidence": confidence,
            "entities": entities or {},
            "agent": agent,
            "turn_count": 1,
            "conversation_id": conversation_id,
        }
    return _gen()


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_session_manager():
    """每个测试前重置全局 SessionManager"""
    session_manager._sessions.clear()
    session_manager._ws_to_session.clear()
    yield


@pytest.fixture
def mock_websocket():
    """创建 Mock WebSocket 对象"""
    ws = MagicMock(spec=WebSocket)
    ws.client = MagicMock()
    ws.client.host = "127.0.0.1"
    ws.send_json = AsyncMock()

    # 模拟 receive_text 行为
    ws.receive_text = AsyncMock()

    return ws


@pytest.fixture
def handler():
    """创建 VoiceWebSocketHandler 并注入 Mock 服务"""
    h = VoiceWebSocketHandler()
    h.asr_service = AsyncMock()
    h.dialog_manager = AsyncMock()
    return h


@pytest.fixture
def connected_session(handler, mock_websocket):
    """创建已连接的会话"""
    return handler.handle_connect(mock_websocket)


@pytest.fixture
def sample_audio_message() -> str:
    """生成模拟音频消息 JSON"""
    audio_bytes = b"\x00\xff" * 8000  # ~16KB 模拟音频
    audio_b64 = base64.b64encode(audio_bytes).decode()
    return json.dumps({
        "type": "audio",
        "data": audio_b64,
        "format": "wav",
        "language": "zh",
    })


@pytest.fixture
def sample_text_message() -> str:
    """生成模拟文本消息 JSON"""
    return json.dumps({
        "type": "text",
        "text": "北京明天天气怎么样",
    })


@pytest.fixture
def sample_ping_message() -> str:
    """生成模拟心跳消息 JSON"""
    return json.dumps({
        "type": "ping",
        "timestamp": 1700000000,
    })


# ============================================================
# Session 管理测试
# ============================================================

class TestSessionManager:
    """会话管理器测试"""

    def test_create_session(self, mock_websocket):
        """测试创建会话"""
        session = session_manager.create_session(mock_websocket)
        assert session is not None
        assert session.session_id is not None
        assert len(session.session_id) == 16
        assert session.client_ip == "127.0.0.1"
        assert session_manager.active_count == 1

    def test_get_by_websocket(self, mock_websocket):
        """测试通过 WebSocket 查找会话"""
        session = session_manager.create_session(mock_websocket)
        found = session_manager.get_by_websocket(mock_websocket)
        assert found is not None
        assert found.session_id == session.session_id

    def test_get_by_session_id(self, mock_websocket):
        """测试通过 session_id 查找会话"""
        session = session_manager.create_session(mock_websocket)
        found = session_manager.get_by_session_id(session.session_id)
        assert found is not None
        assert found.session_id == session.session_id

    def test_get_by_unknown_websocket(self):
        """测试查找不存在的 WebSocket"""
        ws = MagicMock(spec=WebSocket)
        ws.client = MagicMock()
        ws.client.host = "unknown"
        result = session_manager.get_by_websocket(ws)
        assert result is None

    def test_remove_session(self, mock_websocket):
        """测试移除会话"""
        session_manager.create_session(mock_websocket)
        assert session_manager.active_count == 1

        session_manager.remove(mock_websocket)
        assert session_manager.active_count == 0
        assert session_manager.get_by_websocket(mock_websocket) is None

    def test_session_to_dict(self, mock_websocket):
        """测试会话序列化"""
        session = session_manager.create_session(mock_websocket)
        d = session.to_dict()
        assert d["session_id"] == session.session_id
        assert d["client_ip"] == "127.0.0.1"
        assert d["message_count"] == 0

    def test_all_sessions(self, mock_websocket):
        """测试获取所有会话"""
        assert session_manager.all_sessions == {}
        session_manager.create_session(mock_websocket)
        assert len(session_manager.all_sessions) == 1


# ============================================================
# VoiceSession 测试
# ============================================================

class TestVoiceSession:
    """语音会话测试"""

    def test_create_session(self, mock_websocket):
        """测试创建 VoiceSession"""
        session = VoiceSession(mock_websocket)
        assert session.session_id is not None
        assert len(session.session_id) == 16
        assert session.message_count == 0
        assert session.conversation_id == ""

    def test_session_activity_tracking(self, mock_websocket):
        """测试会话活跃时间追踪"""
        import time
        session = VoiceSession(mock_websocket)
        old_time = session.last_active
        session.last_active = time.time() + 1
        assert session.last_active > old_time


# ============================================================
# Handler 连接生命周期测试
# ============================================================

class TestHandlerConnection:
    """Handler 连接生命周期测试"""

    @pytest.mark.asyncio
    async def test_handle_connect(self, handler, mock_websocket):
        """测试连接建立"""
        session = await handler.handle_connect(mock_websocket)

        # 验证 WebSocket 被接受
        mock_websocket.accept.assert_called_once()

        # 验证会话被创建
        assert session is not None
        assert session.session_id is not None

        # 验证 ASR 流式会话被重置
        handler.asr_service.reset_stream.assert_called_once_with(session.session_id)

        # 验证连接确认消息被发送
        mock_websocket.send_json.assert_called_once()
        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "connected"
        assert sent_msg["session_id"] == session.session_id

    @pytest.mark.asyncio
    async def test_handle_connect_without_asr(self, mock_websocket):
        """测试 ASR 未注入时的连接"""
        handler = VoiceWebSocketHandler()
        handler.asr_service = None
        session = await handler.handle_connect(mock_websocket)
        assert session is not None
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_disconnect(self, handler, mock_websocket):
        """测试连接断开"""
        await handler.handle_connect(mock_websocket)
        session_before = session_manager.get_by_websocket(mock_websocket)
        assert session_before is not None

        await handler.handle_disconnect(mock_websocket)
        session_after = session_manager.get_by_websocket(mock_websocket)
        assert session_after is None

    @pytest.mark.asyncio
    async def test_handle_disconnect_unknown_websocket(self, handler):
        """测试断开不存在的连接（不应异常）"""
        # 不应抛出异常
        await handler.handle_disconnect(MagicMock(spec=WebSocket))

    @pytest.mark.asyncio
    async def test_full_connection_lifecycle(self, handler, mock_websocket):
        """测试完整连接生命周期"""
        session = await handler.handle_connect(mock_websocket)
        assert session_manager.active_count == 1

        # 模拟消息处理
        mock_websocket.receive_text.return_value = json.dumps({"type": "ping"})
        # 不主动断开

        await handler.handle_disconnect(mock_websocket)
        assert session_manager.active_count == 0


# ============================================================
# Handler 消息分发测试
# ============================================================

class TestHandlerMessageDispatch:
    """消息分发测试"""

    @pytest.mark.asyncio
    async def test_invalid_json(self, handler, mock_websocket):
        """测试无效 JSON 消息"""
        await handler.handle_connect(mock_websocket)

        await handler.handle_message(mock_websocket, "这不是JSON格式")
        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"
        assert "JSON" in sent_msg["message"] or "格式错误" in sent_msg["message"]

    @pytest.mark.asyncio
    async def test_unknown_message_type(self, handler, mock_websocket):
        """测试未知消息类型"""
        await handler.handle_connect(mock_websocket)

        await handler.handle_message(mock_websocket, json.dumps({"type": "unknown_type"}))
        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_no_session(self, handler, mock_websocket):
        """测试未连接时发送消息"""
        # 不要先调用 handle_connect
        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "你好"}),
        )
        # 应收到"会话不存在"错误
        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_ping_message(self, handler, mock_websocket, sample_ping_message):
        """测试心跳消息"""
        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()  # 清除连接确认消息

        await handler.handle_message(mock_websocket, sample_ping_message)

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "pong"
        assert sent_msg["timestamp"] == 1700000000


# ============================================================
# 音频消息处理测试
# ============================================================

class TestHandlerAudio:
    """音频消息处理测试"""

    @pytest.mark.asyncio
    async def test_audio_message(self, handler, mock_websocket, mock_asr_service):
        """测试音频消息完整链路"""
        handler.asr_service = mock_asr_service
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message = AsyncMock(return_value={
            "conversation_id": "conv_1",
            "response": "当前天气晴朗，温度25°C。",
            "intent": "weather_query",
            "confidence": 0.85,
            "entities": {"city": "北京"},
            "turn_count": 1,
            "state": "idle",
        })

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        # 构建音频消息（带 base64 编码）
        audio_bytes = b"\x00\xff" * 8000
        audio_b64 = base64.b64encode(audio_bytes).decode()
        audio_msg = json.dumps({
            "type": "audio",
            "data": audio_b64,
            "format": "wav",
        })

        await handler.handle_message(mock_websocket, audio_msg)

        # 验证 ASR 流式识别被调用
        mock_asr_service.recognize_stream.assert_called_once()

        # 验证结果消息被发送
        assert mock_websocket.send_json.called
        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] in ("audio_result", "audio_ack")

    @pytest.mark.asyncio
    async def test_audio_message_empty_data(self, handler, mock_websocket):
        """测试空音频数据"""
        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        audio_msg = json.dumps({
            "type": "audio",
            "data": "",
            "format": "wav",
        })

        await handler.handle_message(mock_websocket, audio_msg)

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"
        assert "空" in sent_msg["message"]

    @pytest.mark.asyncio
    async def test_audio_message_invalid_base64(self, handler, mock_websocket):
        """测试无效的 base64 数据"""
        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        audio_msg = json.dumps({
            "type": "audio",
            "data": "这不是base64数据!!!",
            "format": "wav",
        })

        await handler.handle_message(mock_websocket, audio_msg)

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_audio_message_asr_error(self, handler, mock_websocket):
        """测试 ASR 处理异常"""
        handler.asr_service.recognize_stream = AsyncMock(side_effect=Exception("ASR 服务异常"))

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        audio_b64 = base64.b64encode(b"\x00\xff" * 100).decode()
        audio_msg = json.dumps({"type": "audio", "data": audio_b64})

        await handler.handle_message(mock_websocket, audio_msg)

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"
        assert "语音识别" in sent_msg["message"] or "失败" in sent_msg["message"]

    @pytest.mark.asyncio
    async def test_audio_message_asr_no_transcript(self, handler, mock_websocket):
        """测试 ASR 未识别出文本"""
        mock_asr = AsyncMock()
        from app.core.asr import ASRResult
        mock_asr.recognize_stream = AsyncMock(return_value=ASRResult(
            text="", confidence=0.0, language="zh",
        ))
        handler.asr_service = mock_asr

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        audio_b64 = base64.b64encode(b"\x00\xff" * 100).decode()
        audio_msg = json.dumps({"type": "audio", "data": audio_b64})

        await handler.handle_message(mock_websocket, audio_msg)

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "audio_result"
        assert sent_msg["text"] == ""

    @pytest.mark.asyncio
    async def test_audio_message_with_tts(self, handler, mock_websocket, mock_asr_service, mock_ai_voice_service):
        """测试音频消息触发 TTS 合成"""
        from app.core.asr import ASRResult

        # 覆盖 ASR 返回结果（避免 fixture 的 session_id 限制）
        mock_asr = AsyncMock()
        mock_asr.recognize_stream = AsyncMock(return_value=ASRResult(
            text="北京明天天气怎么样", confidence=0.92, language="zh",
        ))
        handler.asr_service = mock_asr

        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="当前天气晴朗，温度25°C。",
                intent="weather_query",
                confidence=0.85,
            )
        )
        handler.ai_voice_service = mock_ai_voice_service

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        audio_b64 = base64.b64encode(b"\x00\xff" * 8000).decode()
        with patch("app.api.websocket.voice_provider_registry.get_active") as mock_get_active, \
             patch("app.api.websocket.voice_provider_registry.get_default") as mock_get_default:
            mock_provider = MagicMock()
            mock_provider.enabled = True
            mock_provider.response_format = "mp3"
            mock_provider.encode_format = "raw"
            mock_get_active.return_value = mock_provider
            mock_get_default.return_value = mock_provider

            await handler.handle_message(
                mock_websocket,
                json.dumps({"type": "audio", "data": audio_b64}),
            )

        # 验证 AI 语音 TTS 被调用
        mock_ai_voice_service._synthesize_stream_call.assert_called_once()


# ============================================================
# 文本消息处理测试
# ============================================================

class TestHandlerText:
    """文本消息处理测试"""

    @pytest.mark.asyncio
    async def test_text_message_greeting(self, handler, mock_websocket):
        """测试问候文本消息（流式 LLM 响应）"""
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="你好！我是AI语音助手，请问有什么可以帮助您的？",
                intent="general_chat",
                confidence=0.80,
            )
        )

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "你好"}),
        )

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "stream_end"
        assert sent_msg["intent"] == "general_chat"
        assert "你好" in sent_msg["full_text"]

    @pytest.mark.asyncio
    async def test_text_message_weather(self, handler, mock_websocket):
        """测试天气查询文本消息（流式 LLM 响应）"""
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="当前天气晴朗，温度25°C。",
                intent="weather_query",
                confidence=0.85,
                entities={"city": "北京"},
            )
        )

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "北京天气"}),
        )

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "stream_end"
        assert sent_msg["intent"] == "weather_query"

    @pytest.mark.asyncio
    async def test_text_message_empty(self, handler, mock_websocket):
        """测试空文本消息"""
        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": ""}),
        )

        sent_msg = mock_websocket.send_json.call_args[0][0]
        assert sent_msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_text_message_no_dialog(self, handler, mock_websocket):
        """测试 DialogManager 未注入"""
        handler.dialog_manager = None

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "你好"}),
        )

        sent_msg = mock_websocket.send_json.call_args[0][0]
        # 没有 DialogManager 时，返回错误提示
        assert sent_msg["type"] == "error"

    @pytest.mark.asyncio
    async def test_text_message_no_tts(self, handler, mock_websocket, mock_ai_voice_service):
        """测试文本消息不触发 TTS（仅语音消息触发 TTS）"""
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="你好！",
                intent="general_chat",
                confidence=0.80,
            )
        )
        handler.ai_voice_service = mock_ai_voice_service

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "你好"}),
        )

        # 文本消息不应触发 TTS
        mock_ai_voice_service.synthesize.assert_not_called()
        mock_ai_voice_service._synthesize_stream_call.assert_not_called()


# ============================================================
# TTS 辅助方法测试
# ============================================================

class TestHandlerTTS:
    """TTS 辅助方法测试（使用 AI 语音大模型）"""

    @pytest.mark.asyncio
    async def test_tts_stream_and_send_success(self, handler, mock_websocket, mock_ai_voice_service):
        """测试 TTS 流式合成成功"""
        handler.ai_voice_service = mock_ai_voice_service
        session = await handler.handle_connect(mock_websocket)

        with patch("app.api.websocket.voice_provider_registry.get_active") as mock_get_active, \
             patch("app.api.websocket.voice_provider_registry.get_default") as mock_get_default:
            mock_provider = MagicMock()
            mock_provider.enabled = True
            mock_provider.response_format = "mp3"
            mock_provider.encode_format = "raw"
            mock_get_active.return_value = mock_provider
            mock_get_default.return_value = mock_provider

            await handler._tts_stream_and_send(session, "你好世界")

        mock_ai_voice_service._synthesize_stream_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_tts_stream_and_send_no_service(self, handler, mock_websocket):
        """测试 TTS 服务未注入时跳过"""
        handler.ai_voice_service = None
        session = await handler.handle_connect(mock_websocket)

        # 不应抛出异常
        await handler._tts_stream_and_send(session, "你好世界")

    @pytest.mark.asyncio
    async def test_tts_stream_and_send_empty_text(self, handler, mock_websocket, mock_ai_voice_service):
        """测试空文本不触发 TTS"""
        handler.ai_voice_service = mock_ai_voice_service
        session = await handler.handle_connect(mock_websocket)

        await handler._tts_stream_and_send(session, "")

        mock_ai_voice_service.synthesize.assert_not_called()
        mock_ai_voice_service._synthesize_stream_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_stream_and_send_failure_graceful(self, handler, mock_websocket):
        """测试 TTS 合成失败不应影响主流程"""
        mock_ai = AsyncMock()
        mock_ai.synthesize_stream = AsyncMock(side_effect=Exception("TTS 失败"))
        handler.ai_voice_service = mock_ai

        session = await handler.handle_connect(mock_websocket)

        with patch("app.api.websocket.voice_provider_registry.get_active") as mock_get_active:
            mock_provider = MagicMock()
            mock_provider.enabled = True
            mock_get_active.return_value = mock_provider

            # 不应抛出异常
            await handler._tts_stream_and_send(session, "你好")


# ============================================================
# 多消息场景测试
# ============================================================

class TestHandlerMultiMessage:
    """多消息场景测试"""

    @pytest.mark.asyncio
    async def test_text_then_text(self, handler, mock_websocket):
        """测试连续文本消息"""
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="回复内容",
                intent="general_chat",
                confidence=0.50,
            )
        )

        await handler.handle_connect(mock_websocket)

        # 发送两条文本
        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "第一条消息"}),
        )
        await handler.handle_message(
            mock_websocket,
            json.dumps({"type": "text", "text": "第二条消息"}),
        )

        # DialogManager 流式接口应被调用两次
        assert handler.dialog_manager.process_message_stream.call_count == 2

    @pytest.mark.asyncio
    async def test_ping_in_between(self, handler, mock_websocket):
        """测试消息间插入心跳"""
        handler.dialog_manager = MagicMock()
        handler.dialog_manager.process_message = AsyncMock(return_value={
            "conversation_id": "conv_1",
            "response": "回复",
            "intent": "general_chat",
            "confidence": 0.50,
            "entities": {},
            "turn_count": 1,
            "state": "idle",
        })

        await handler.handle_connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        # 文本 → ping → 文本
        await handler.handle_message(
            mock_websocket, json.dumps({"type": "text", "text": "你好"}),
        )
        await handler.handle_message(
            mock_websocket, json.dumps({"type": "ping", "timestamp": 100}),
        )
        await handler.handle_message(
            mock_websocket, json.dumps({"type": "text", "text": "天气"}),
        )

        # 验证 ping 回复
        # send_json 被调用多次，检查其中包含 pong
        call_args_list = mock_websocket.send_json.call_args_list
        pong_calls = [
            args[0][0] for args in call_args_list
            if args[0][0].get("type") == "pong"
        ]
        assert len(pong_calls) == 1
        assert pong_calls[0]["timestamp"] == 100


# ============================================================
# WebSocket 端点集成测试（使用 Mock）
# ============================================================

class TestWebSocketEndpoint:
    """WebSocket 端点集成测试"""

    @pytest.mark.asyncio
    async def test_voice_websocket_endpoint_connect(self, mock_websocket):
        """测试端点连接流程"""
        from app.api.websocket import voice_websocket_endpoint

        mock_websocket.receive_text.side_effect = WebSocketDisconnect()

        await voice_websocket_endpoint(mock_websocket)

        # 验证 WebSocket 被接受
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_voice_websocket_endpoint_message_then_disconnect(self, mock_websocket):
        """测试端点连接 → 消息 → 断开流程"""
        from app.api.websocket import voice_websocket_endpoint, voice_handler

        # 注入 Mock 服务
        voice_handler.asr_service = None
        voice_handler.dialog_manager = MagicMock()
        voice_handler.dialog_manager.process_message_stream = MagicMock(
            return_value=mock_stream_result(
                response="你好！",
                intent="general_chat",
                confidence=0.80,
            )
        )
        voice_handler.ai_voice_service = None

        # 模拟消息循环：先收到一条消息，然后断开
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "text", "text": "你好"}),
            WebSocketDisconnect(),
        ]

        await voice_websocket_endpoint(mock_websocket)

        # 验证连接被接受
        mock_websocket.accept.assert_called_once()

        # 验证 DialogManager 流式接口被调用
        voice_handler.dialog_manager.process_message_stream.assert_called_once()
