"""
对话管理模块 (Dialog Manager)
负责任务调度、上下文管理和多轮对话

核心功能:
  1. 多轮对话 — 每个 session 维护最近 10 轮对话历史
  2. 状态机 — IDLE → LISTENING → PROCESSING → RESPONDING
  3. 意图路由 — 功能类意图调 FunctionService，聊天类意图调 LLM
  4. 上下文感知 — 结合历史对话生成更准确的回复
  5. 会话超时清理 — 30 分钟无活动自动清除
"""

import asyncio
import hashlib
import json
import logging
import re
import time as time_module
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List

import httpx

from app.core.config import settings, runtime_config
from app.core.http_client import get_http_client
from app.core.llm_providers import provider_registry
from app.core.nlu import NLUService, Intent
from app.core.multi_agent import agent_orchestrator, agent_registry
from app.functions.services import FunctionService

# headroom-ai: 智能上下文压缩，降低 LLM API Token 消耗
try:
    from headroom import compress as _headroom_compress
    HEADROOM_AVAILABLE = True
except ImportError:
    HEADROOM_AVAILABLE = False
    _headroom_compress = None

logger = logging.getLogger("voice-assistant.dialog")

# ============================================================
# LLM 响应缓存
# ============================================================
class LLMResponseCache:
    """LLM 响应语义缓存（基于输入文本哈希）

    相同或高度相似的问题在 TTL 内直接返回缓存结果，
    避免重复调用 LLM API，降低延迟和费用。
    """

    def __init__(self, max_size: int = 256, ttl: int = 300):
        self._max_size = max_size
        self._ttl = ttl  # 缓存有效期（秒）
        self._cache: OrderedDict = OrderedDict()

    def _make_key(self, text: str, history: str) -> str:
        """生成缓存键（文本 + 最近历史摘要）"""
        raw = f"{text}|{history[:100]}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get(self, text: str, history: str) -> Optional[str]:
        """获取缓存（过期返回 None）"""
        key = self._make_key(text, history)
        entry = self._cache.get(key)
        if entry is None:
            return None
        timestamp, response = entry
        if time_module.time() - timestamp > self._ttl:
            del self._cache[key]
            return None
        # LRU 更新
        self._cache.move_to_end(key)
        logger.debug(f"[LLM缓存] 命中: text=\"{text[:30]}...\"")
        return response

    def put(self, text: str, history: str, response: str):
        """存入缓存"""
        key = self._make_key(text, history)
        self._cache[key] = (time_module.time(), response)
        self._cache.move_to_end(key)
        # LRU 淘汰
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._cache)

# 全局 LLM 缓存实例
_llm_cache = LLMResponseCache(
    max_size=getattr(settings, "LLM_CACHE_SIZE", 256),
    ttl=getattr(settings, "LLM_CACHE_TTL", 300),
)

# 会话超时时间（分钟）
SESSION_TIMEOUT_MINUTES = 30


# ============================================================
# 状态机定义
# ============================================================
class SessionState(str, Enum):
    """对话状态机

    状态流转:
      IDLE ──(收到消息)──→ LISTENING ──(接收完毕)──→ PROCESSING
      PROCESSING ──(路由完成)──→ RESPONDING ──(回复发送)──→ IDLE
    """
    IDLE = "idle"               # 空闲，等待用户输入
    LISTENING = "listening"     # 正在接收用户输入（语音场景）
    PROCESSING = "processing"   # NLU 解析 + 意图路由
    RESPONDING = "responding"   # 生成回复中
    ERROR = "error"             # 异常状态


# ============================================================
# 会话上下文
# ============================================================
class ConversationContext:
    """单个会话的上下文容器"""

    def __init__(self, session_id: str):
        self.session_id = session_id           # 会话唯一标识
        self.history: List[Dict[str, str]] = []  # 对话历史
        self.metadata: Dict[str, Any] = {}       # 扩展元数据
        self.current_intent: Optional[Intent] = None  # 当前意图
        self.state: SessionState = SessionState.IDLE  # 当前状态
        self.created_at: datetime = datetime.now()    # 创建时间
        self.updated_at: datetime = datetime.now()    # 最后活动时间

        # 配置
        self._max_history_turns = 10  # 保留最近 10 轮对话

    # ---- 历史管理 ----

    def add_message(self, role: str, content: str):
        """添加一条消息到对话历史"""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        # 超出上限时裁掉最早的历史（每轮 = user + assistant 两条）
        max_entries = self._max_history_turns * 2
        if len(self.history) > max_entries:
            self.history = self.history[-max_entries:]
        self.updated_at = datetime.now()

    def get_history_text(self, max_turns: int = 10) -> str:
        """将最近 N 轮历史拼接为文本（用于 LLM 上下文）"""
        max_entries = max_turns * 2
        recent = self.history[-max_entries:] if len(self.history) > max_entries else self.history
        return "\n".join(
            f"{'用户' if msg['role'] == 'user' else '助手'}: {msg['content']}"
            for msg in recent
        )

    def get_history_messages(self, max_turns: int = 10) -> List[Dict[str, str]]:
        """将最近 N 轮历史转为 OpenAI 消息格式"""
        max_entries = max_turns * 2
        recent = self.history[-max_entries:] if len(self.history) > max_entries else self.history
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in recent
        ]

    # ---- 超时检测 ----

    def is_expired(self, timeout_minutes: int = SESSION_TIMEOUT_MINUTES) -> bool:
        """检查会话是否已超时"""
        elapsed = datetime.now() - self.updated_at
        return elapsed > timedelta(minutes=timeout_minutes)

    # ---- 状态机辅助 ----

    @property
    def turn_count(self) -> int:
        """当前对话轮数"""
        return len(self.history) // 2

    def reset_state(self):
        """重置状态到 IDLE"""
        self.state = SessionState.IDLE


# ============================================================
# 对话管理器
# ============================================================
class DialogManager:
    """对话管理器 — 统一对外接口

    用法:
        dm = DialogManager()
        result = await dm.process_message("北京天气", "session_xxx")
    """

    def __init__(self, db_service=None):
        self.nlu = NLUService()
        self.function_service = FunctionService()
        self.conversations: Dict[str, ConversationContext] = {}
        self.db_service = db_service  # 可选的数据库持久化服务

    # ============================================================
    # 会话生命周期
    # ============================================================

    def create_conversation(self, session_id: Optional[str] = None) -> str:
        """创建一个新的会话"""
        conv_id = session_id or str(uuid.uuid4())
        self.conversations[conv_id] = ConversationContext(session_id=conv_id)
        logger.info(f"[Dialog] 创建新会话: {conv_id}")
        # 持久化到数据库（如果可用）
        if self.db_service:
            asyncio.ensure_future(self.db_service.save_conversation(conv_id))
        return conv_id

    def get_conversation(self, conversation_id: str) -> Optional[ConversationContext]:
        """获取已有会话上下文"""
        return self.conversations.get(conversation_id)

    # ============================================================
    # 【新增】Agent 关键词预检
    # ============================================================

    @staticmethod
    def _build_agent_keywords() -> Dict[str, List[str]]:
        """
        从 AgentRegistry 动态构建智能体 → 关键词映射表

        每个专精智能体的 name + description 自动生成匹配关键词，
        无需手动维护，AgentRegistry 新增智能体时自动生效。
        """
        keywords_map = {}
        # 预置 Agent-specific 关键词（与智能体角色匹配）
        preset_keywords = {
            "code_expert": [
                "写代码", "编程", "debug", "调试", "程序", "代码", "bug",
                "python", "javascript", "java", "golang", "rust",
                "函数", "算法", "接口", "重构", "优化代码",
            ],
            "creative": [
                "写诗", "作诗", "写故事", "写文章", "文案", "创意",
                "小说", "诗歌", "作文", "起名", "取名", "脑洞",
                "灵感", "创作", "写作",
            ],
            "translator": [
                "翻译", "translate", "翻译成", "译成",
                "英文怎么说", "中文怎么说", "英译中", "中译英",
                "翻一下", "翻成",
            ],
            "analyst": [
                "数据分析", "分析数据", "统计", "数学",
                "逻辑", "推理", "图表", "对比", "趋势",
                "计算一下", "算一下",
            ],
        }

        # 从 AgentRegistry 获取已启用的专精智能体
        specialists = agent_registry.get_specialists()
        for name, cfg in specialists.items():
            if name == "general_chat":
                continue
            # 取预置关键词，没有则从描述中抽取关键词
            if name in preset_keywords:
                keywords_map[name] = preset_keywords[name]
            else:
                # 从 description 中自动提取关键词（按空格/逗号分割）
                desc_keywords = re.split(r'[、，,.\s]+', cfg.description)
                desc_keywords = [kw for kw in desc_keywords if len(kw) >= 2]
                keywords_map[name] = desc_keywords[:10]  # 最多取 10 个

        return keywords_map

    def _precheck_agent_route(self, text: str) -> Optional[str]:
        """
        轻量级预检：关键词匹配 → 快速识别是否需要路由到专精智能体

        在 NLU.parse() 之前执行，零 LLM 调用开销。
        如果匹配到某个专精智能体的关键词，直接返回该智能体名称。
        未匹配返回 None，走正常 NLU 流程。

        匹配策略:
          - 命中 1+ 个关键词 → 返回对应的智能体名称
          - 命中多个智能体的关键词 → 返回命中数最多的
        """
        keywords_map = self._build_agent_keywords()
        if not keywords_map:
            return None

        # 统计各智能体的命中数
        hit_counts: Dict[str, int] = {}
        for agent_name, keywords in keywords_map.items():
            count = 0
            for kw in keywords:
                if kw in text:
                    count += 1
            if count > 0:
                hit_counts[agent_name] = count

        if not hit_counts:
            return None

        # 取命中数最多的智能体
        best_agent = max(hit_counts, key=hit_counts.get)
        best_count = hit_counts[best_agent]

        logger.debug(
            f"[Dialog-预检] text=\"{text[:20]}...\" "
            f"→ agent={best_agent} (命中{best_count}个关键词, "
            f"候选={hit_counts})"
        )
        return best_agent

    # ============================================================
    # 核心入口
    # ============================================================

    async def process_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        处理用户消息

        流程:
          IDLE → PROCESSING → [预检] → NLU → 意图路由 → RESPONDING → IDLE

        【优化】预检阶段：在 NLU 解析之前，先通过关键词快速匹配专精智能体。
        如果匹配成功，直接路由到对应的专精智能体，跳过 NLU。

        参数:
            message: 用户输入的文本
            conversation_id: 会话 ID（None 则自动创建）

        返回:
            {
                "conversation_id": str,
                "response": str,
                "intent": str,
                "confidence": float,
                "entities": dict,
                "turn_count": int,
                "state": str,
            }
        """
        message = message.strip()
        if not message:
            return self._build_response(
                conversation_id=conversation_id or "",
                response="请说点什么吧。",
                intent="general_chat",
                confidence=0.0,
                entities={},
            )

        # ---- 1. 获取或创建会话 ----
        context = self._get_or_create(conversation_id)

        # 检查会话是否超时，超时则新建（保留 session_id）
        if context.is_expired():
            logger.info(f"[Dialog] 会话 {context.session_id} 已超时 ({SESSION_TIMEOUT_MINUTES}min)，自动新建")
            self.conversations[context.session_id] = ConversationContext(
                session_id=context.session_id,
            )
            context = self.conversations[context.session_id]

        # ---- 2. 状态更新 + 保存消息 ----
        context.state = SessionState.PROCESSING
        context.add_message("user", message)

        # 持久化用户消息到数据库
        if self.db_service:
            asyncio.ensure_future(
                self.db_service.save_message(
                    conversation_id=context.session_id,
                    role="user",
                    content=message,
                )
            )

        # ---- 3. 【新增】Agent 预检（NLU 前置） ----
        # 通过关键词快速匹配专精智能体，零 LLM 调用开销
        prechecked_agent = self._precheck_agent_route(message)
        if prechecked_agent:
            specialists = agent_registry.get_specialists()
            agent = specialists.get(prechecked_agent)
            if agent:
                logger.info(
                    f"[Dialog] 预检路由: \"{message[:30]}...\" "
                    f"→ agent={agent.name} ({agent.display_name})"
                )
                # 保存智能体信息
                context.metadata["last_agent"] = {
                    "name": agent.name,
                    "display_name": agent.display_name,
                    "reason": "预检关键词匹配",
                }
                # 直接调用智能体，跳过 NLU
                history_messages = context.get_history_messages(max_turns=5)
                response = await agent_orchestrator._call_agent(
                    agent=agent,
                    user_message=message,
                    context_messages=history_messages,
                )
                # 保存回复 + 状态恢复
                context.add_message("assistant", response)
                context.state = SessionState.IDLE
                return self._build_response(
                    conversation_id=context.session_id,
                    response=response,
                    intent=prechecked_agent,
                    confidence=0.85,
                    entities={"raw_text": message, "agent_request": True},
                    turn_count=context.turn_count,
                    state=context.state.value,
                    agent_info=context.metadata["last_agent"],
                )

        # ---- 4. NLU 解析 ----
        intent = await self.nlu.parse(message)
        context.current_intent = intent

        # ---- 5. 意图路由 ----
        response = await self._route(intent, context)

        # ---- 5. 保存回复 + 状态恢复 ----
        context.add_message("assistant", response)
        context.state = SessionState.IDLE

        # 持久化助手回复到数据库
        if self.db_service:
            asyncio.ensure_future(
                self.db_service.save_message(
                    conversation_id=context.session_id,
                    role="assistant",
                    content=response,
                    intent=intent.name,
                    confidence=intent.confidence,
                    entities=intent.entities,
                )
            )

        logger.info(
            f"[Dialog] 处理完成: session={context.session_id}, "
            f"intent={intent.name}({intent.confidence:.2f}), "
            f"轮次={context.turn_count}"
        )

        # ---- 6. 提取智能体信息 ----
        agent_info = context.metadata.pop("last_agent", None)

        return self._build_response(
            conversation_id=context.session_id,
            response=response,
            intent=intent.name,
            confidence=intent.confidence,
            entities=intent.entities,
            turn_count=context.turn_count,
            state=context.state.value,
            agent_info=agent_info,
        )

    async def process_message_stream(
        self,
        message: str,
        conversation_id: Optional[str] = None,
    ):
        """
        流式处理用户消息

        与 process_message 的行为保持一致，但 LLM 生成回复时逐块 yield：
          {"type": "meta", "intent": ..., "confidence": ..., "entities": ..., "agent": ...}
          {"type": "delta", "delta": "..."}
          {"type": "stream_end", "full_text": "...", "intent": ..., "agent": ..., "turn_count": ...}

        功能类意图（天气/设备/日程/音乐）直接返回完整文本，不触发 LLM 流式。
        """
        message = message.strip()
        if not message:
            yield {
                "type": "stream_end",
                "full_text": "请说点什么吧。",
                "intent": "general_chat",
                "confidence": 0.0,
                "entities": {},
                "turn_count": 0,
            }
            return

        # ---- 1. 获取或创建会话 ----
        context = self._get_or_create(conversation_id)

        # 检查会话是否超时，超时则新建（保留 session_id）
        if context.is_expired():
            logger.info(
                f"[Dialog] 会话 {context.session_id} 已超时 ({SESSION_TIMEOUT_MINUTES}min)，自动新建"
            )
            self.conversations[context.session_id] = ConversationContext(
                session_id=context.session_id,
            )
            context = self.conversations[context.session_id]

        # ---- 2. 状态更新 + 保存消息 ----
        context.state = SessionState.PROCESSING
        context.add_message("user", message)

        # 持久化用户消息到数据库
        if self.db_service:
            asyncio.ensure_future(
                self.db_service.save_message(
                    conversation_id=context.session_id,
                    role="user",
                    content=message,
                )
            )

        # ---- 3. Agent 预检（NLU 前置） ----
        prechecked_agent = self._precheck_agent_route(message)
        if prechecked_agent:
            specialists = agent_registry.get_specialists()
            agent = specialists.get(prechecked_agent)
            if agent:
                logger.info(
                    f"[Dialog-Stream] 预检路由: \"{message[:30]}...\" "
                    f"→ agent={agent.name} ({agent.display_name})"
                )
                context.metadata["last_agent"] = {
                    "name": agent.name,
                    "display_name": agent.display_name,
                    "reason": "预检关键词匹配",
                }
                history_messages = context.get_history_messages(max_turns=5)
                yield {
                    "type": "meta",
                    "intent": prechecked_agent,
                    "confidence": 0.85,
                    "entities": {"raw_text": message, "agent_request": True},
                    "agent": context.metadata["last_agent"],
                }

                reply_text = ""
                async for delta in agent_orchestrator._call_agent_stream(
                    agent=agent,
                    user_message=message,
                    context_messages=history_messages,
                ):
                    reply_text += delta
                    yield {"type": "delta", "delta": delta}

                context.add_message("assistant", reply_text)
                context.state = SessionState.IDLE
                if self.db_service:
                    asyncio.ensure_future(
                        self.db_service.save_message(
                            conversation_id=context.session_id,
                            role="assistant",
                            content=reply_text,
                            intent=prechecked_agent,
                            confidence=0.85,
                            entities={"raw_text": message, "agent_request": True},
                        )
                    )
                yield {
                    "type": "stream_end",
                    "full_text": reply_text,
                    "intent": prechecked_agent,
                    "confidence": 0.85,
                    "entities": {"raw_text": message, "agent_request": True},
                    "agent": context.metadata["last_agent"],
                    "turn_count": context.turn_count,
                    "conversation_id": context.session_id,
                }
                return

        # ---- 4. NLU 解析 ----
        intent = await self.nlu.parse(message)
        context.current_intent = intent

        # ---- 5. 功能类意图直接返回完整文本（不流式） ----
        if intent.name in ("weather_query", "device_control", "schedule", "music_play"):
            response = await self._route(intent, context)
            yield {
                "type": "meta",
                "intent": intent.name,
                "confidence": intent.confidence,
                "entities": intent.entities,
            }
            context.add_message("assistant", response)
            context.state = SessionState.IDLE
            if self.db_service:
                asyncio.ensure_future(
                    self.db_service.save_message(
                        conversation_id=context.session_id,
                        role="assistant",
                        content=response,
                        intent=intent.name,
                        confidence=intent.confidence,
                        entities=intent.entities,
                    )
                )
            yield {
                "type": "stream_end",
                "full_text": response,
                "intent": intent.name,
                "confidence": intent.confidence,
                "entities": intent.entities,
                "turn_count": context.turn_count,
                "conversation_id": context.session_id,
            }
            return

        # ---- 6. 智能体直连路由 ----
        if intent.entities.get("agent_request") is True:
            specialists = agent_registry.get_specialists()
            if intent.name in specialists:
                agent = specialists[intent.name]
                text = intent.entities.get("raw_text", "")
                logger.info(
                    f"[Dialog-Stream] 智能体直连路由: intent={intent.name} "
                    f"→ agent={agent.display_name}"
                )
                context.metadata["last_agent"] = {
                    "name": agent.name,
                    "display_name": agent.display_name,
                    "reason": "NLU 直接识别到智能体意图",
                }
                yield {
                    "type": "meta",
                    "intent": intent.name,
                    "confidence": intent.confidence,
                    "entities": intent.entities,
                    "agent": context.metadata["last_agent"],
                }

                reply_text = ""
                async for delta in agent_orchestrator._call_agent_stream(
                    agent=agent,
                    user_message=text,
                    context_messages=context.get_history_messages(max_turns=5),
                ):
                    reply_text += delta
                    yield {"type": "delta", "delta": delta}

                context.add_message("assistant", reply_text)
                context.state = SessionState.IDLE
                if self.db_service:
                    asyncio.ensure_future(
                        self.db_service.save_message(
                            conversation_id=context.session_id,
                            role="assistant",
                            content=reply_text,
                            intent=intent.name,
                            confidence=intent.confidence,
                            entities=intent.entities,
                        )
                    )
                yield {
                    "type": "stream_end",
                    "full_text": reply_text,
                    "intent": intent.name,
                    "confidence": intent.confidence,
                    "entities": intent.entities,
                    "agent": context.metadata["last_agent"],
                    "turn_count": context.turn_count,
                    "conversation_id": context.session_id,
                }
                return

        # ---- 7. 聊天类意图：通用聊天 / 多智能体协同 ----
        text = intent.entities.get("raw_text", "")
        specialists = agent_registry.get_specialists()
        other_specialists = {
            name: cfg for name, cfg in specialists.items() if name != "general_chat"
        }
        has_specialist_agents = len(other_specialists) >= 1

        yield {
            "type": "meta",
            "intent": intent.name,
            "confidence": intent.confidence,
            "entities": intent.entities,
        }

        reply_text = ""
        if has_specialist_agents:
            async for event in agent_orchestrator.route_and_respond_stream(
                user_message=text,
                conversation_history=context.get_history_text(max_turns=5),
                context_messages=context.get_history_messages(max_turns=5),
            ):
                if event["type"] == "delta":
                    reply_text += event["delta"]
                    yield event
                elif event["type"] == "meta" and event.get("agent"):
                    context.metadata["last_agent"] = event["agent"]
        else:
            local = self._local_chat(text)
            if local:
                reply_text = local
                yield {"type": "delta", "delta": local}
            else:
                async for delta in self._call_llm_stream(text, context):
                    reply_text += delta
                    yield {"type": "delta", "delta": delta}

        context.add_message("assistant", reply_text)
        context.state = SessionState.IDLE
        if self.db_service:
            asyncio.ensure_future(
                self.db_service.save_message(
                    conversation_id=context.session_id,
                    role="assistant",
                    content=reply_text,
                    intent=intent.name,
                    confidence=intent.confidence,
                    entities=intent.entities,
                )
            )

        agent_info = context.metadata.pop("last_agent", None)
        logger.info(
            f"[Dialog-Stream] 处理完成: session={context.session_id}, "
            f"intent={intent.name}({intent.confidence:.2f}), 轮次={context.turn_count}"
        )
        yield {
            "type": "stream_end",
            "full_text": reply_text,
            "intent": intent.name,
            "confidence": intent.confidence,
            "entities": intent.entities,
            "agent": agent_info,
            "turn_count": context.turn_count,
            "conversation_id": context.session_id,
        }

    # ============================================================
    # 意图路由
    # ============================================================

    async def _route(self, intent: Intent, context: ConversationContext) -> str:
        """
        根据意图类型选择处理策略:
          - 功能类意图 → FunctionService（天气/设备）
          - 规则意图 → 本地规则（日程/音乐，暂未对接外部接口）
          - 智能体意图 → 如果 intent.name 匹配某个专精智能体，直接定向路由
          - 聊天类意图 → 多智能体协同或 LLM API
        """
        routing_map = {
            "weather_query": self._handle_weather,
            "device_control": self._handle_device_control,
            "schedule": self._handle_schedule,
            "music_play": self._handle_music_play,
        }

        handler = routing_map.get(intent.name)
        if handler is not None:
            return await handler(intent, context)

        # ---- 【新增】智能体意图直连路由 ----
        # 当 NLU（LLM 分类器）识别出 intent.name 是某个专精智能体时，
        # 直接让该智能体处理，而非走通用聊天流程
        if intent.entities.get("agent_request") is True:
            specialists = agent_registry.get_specialists()
            if intent.name in specialists:
                agent = specialists[intent.name]
                text = intent.entities.get("raw_text", "")
                logger.info(
                    f"[Dialog] 智能体直连路由: intent={intent.name} "
                    f"→ agent={agent.display_name}"
                )
                # 保存智能体路由信息到上下文
                context.metadata["last_agent"] = {
                    "name": agent.name,
                    "display_name": agent.display_name,
                    "reason": "NLU 直接识别到智能体意图",
                }
                # 调用智能体生成回复
                history_messages = context.get_history_messages(max_turns=5)
                response = await agent_orchestrator._call_agent(
                    agent=agent,
                    user_message=text,
                    context_messages=history_messages,
                )
                return response

        # 兜底：聊天类意图
        return await self._handle_general_chat(intent, context)

    # ============================================================
    # 功能类意图处理器（调用 FunctionService）
    # ============================================================

    async def _handle_weather(self, intent: Intent, context: ConversationContext) -> str:
        """天气查询 → FunctionService.get_weather"""
        city = intent.entities.get("city", "")

        if not city:
            # 尝试从历史中补全城市
            city = self._extract_city_from_history(context)
            if not city:
                return "请问您想查询哪个城市的天气？"

        try:
            result = await self.function_service.execute("get_weather", {"city": city})
            if result.get("temperature") and result["temperature"] != "N/A":
                return (
                    f"{city}当前天气：{result['weather']}，"
                    f"温度{result['temperature']}，"
                    f"湿度{result['humidity']}，"
                    f"风力{result['wind']}。"
                )
            return f"抱歉，暂时无法获取{city}的天气信息。"
        except Exception as e:
            logger.error(f"[Dialog] 天气查询异常: {e}")
            return f"查询{city}天气时出现错误，请稍后再试。"

    async def _handle_device_control(self, intent: Intent, context: ConversationContext) -> str:
        """设备控制 → FunctionService.control_device"""
        device = intent.entities.get("device", "")
        action = intent.entities.get("action", "")

        if not device:
            return "请告诉我要控制哪个设备？（如：灯、空调、电视）"
        if not action:
            return f"要对{device}执行什么操作？（如：打开、关闭）"

        # 实体 → FunctionService 参数映射
        device_map = {
            "灯": "light_1",      "灯光": "light_1",
            "空调": "ac_1",
            "电视": "tv_1",       "电视机": "tv_1",
            "窗帘": "curtain_1",
            "风扇": "light_2",
        }
        action_map = {
            "打开": "turn_on",    "开": "turn_on",    "开启": "turn_on",
            "关闭": "turn_off",   "关": "turn_off",   "关闭": "turn_off",
        }

        device_id = device_map.get(device)
        if not device_id:
            return f"暂不支持控制 {device}，目前支持的设备：灯、空调、电视、窗帘"

        action_id = action_map.get(action)
        if not action_id:
            return f"不支持的操作：{action}（支持：打开/关闭）"

        try:
            result = await self.function_service.execute(
                "control_device",
                {"device_id": device_id, "action": action_id},
            )
            if result.get("success"):
                return result["message"]
            return f"控制失败：{result.get('message', '未知错误')}"
        except Exception as e:
            logger.error(f"[Dialog] 设备控制异常: {e}")
            return f"控制{device}时出现错误，请稍后再试。"

    # ============================================================
    # 规则类意图处理器（本地逻辑）
    # ============================================================

    async def _handle_schedule(self, intent: Intent, context: ConversationContext) -> str:
        """日程管理 — 本地规则处理"""
        event = intent.entities.get("event_name", "")
        date = intent.entities.get("date", "")
        time = intent.entities.get("time", "")

        if event and date:
            return f"已为您记录日程：{date} {time} {event}"
        if date:
            return f"正在查询{date}的日程安排..."
        return "请告诉我您想设置什么提醒或查询哪天的日程？"

    async def _handle_music_play(self, intent: Intent, context: ConversationContext) -> str:
        """音乐播放 — 本地规则处理"""
        artist = intent.entities.get("artist", "")
        song = intent.entities.get("song", "")
        genre = intent.entities.get("genre", "")

        if artist and song:
            return f"正在为您播放{artist}的{song}..."
        if artist:
            return f"正在为您播放{artist}的热门歌曲..."
        if genre:
            return f"正在为您播放{genre}音乐..."
        if song:
            return f"正在为您播放{song}..."
        return "正在为您播放音乐..."

    # ============================================================
    # 聊天类意图处理器（LLM + 本地兜底）
    # ============================================================

    async def _handle_general_chat(self, intent: Intent, context: ConversationContext) -> str:
        """
        通用聊天（增强版）— 多智能体协同处理

        流程:
          1. 【新增】检测是否有多个专精智能体启用 → 有则直接走 Orchestrator 语义路由
          2. 本地规则匹配常见问候场景（避免不必要的 API 调用）
          3. 通过智能体协调者进行路由判别，选择合适的专精智能体
          4. 专精智能体生成回复
        """
        text = intent.entities.get("raw_text", "")

        # ---- 【新增】获取已启用的专精智能体数量 ----
        specialists = agent_registry.get_specialists()
        # 排除 general_chat 自身，统计其他专精智能体数量
        other_specialists = {
            name: cfg for name, cfg in specialists.items()
            if name != "general_chat"
        }
        has_specialist_agents = len(other_specialists) >= 1

        # ---- 【优化】有专精智能体时，直接走 Orchestrator 语义路由 ----
        # Orchestrator 内部使用 LLM 进行语义理解，能识别"翻译/写代码/写诗"等意图
        # 替代原来的"先 local_chat 匹配固定关键词"的局限
        if has_specialist_agents:
            return await self._route_to_orchestrator(text, context)

        # ---- 无专精智能体时，使用本地规则匹配常见场景（避免不必要的 API 调用） ----
        local = self._local_chat(text)
        if local:
            return local

        # ---- 回退到 Orchestrator + LLM ----
        return await self._route_to_orchestrator(text, context)

    async def _route_to_orchestrator(
        self, text: str, context: ConversationContext
    ) -> str:
        """
        通过 Orchestrator 进行多智能体语义路由

        由 Orchestrator 根据用户消息语义自动选择最合适的专精智能体，
        而非硬编码的意图匹配。
        """
        history_text = context.get_history_text(max_turns=5)
        history_messages = context.get_history_messages(max_turns=5)

        try:
            result = await agent_orchestrator.route_and_respond(
                user_message=text,
                conversation_history=history_text,
                context_messages=history_messages,
            )
            # 保存智能体信息到上下文元数据
            context.metadata["last_agent"] = {
                "name": result["agent_name"],
                "display_name": result["agent_display_name"],
                "reason": result["reason"],
            }
            return result["response"]

        except Exception as e:
            logger.error(f"[Dialog] 多智能体协同异常，回退到直接 LLM 调用: {e}", exc_info=True)
            return await self._call_llm(text, context)

    def _local_chat(self, text: str) -> Optional[str]:
        """本地规则回复 — 问候/感谢/告别等高频场景"""
        rules = [
            # (关键词列表, 回复)
            (["你好", "您好", "嗨", "hi", "hello", "早上好", "下午好", "晚上好"],
             "你好！我是AI语音助手，请问有什么可以帮助您的？"),
            (["谢谢", "感谢"],
             "不客气！很高兴能帮到您，还有其他需要吗？"),
            (["你会什么", "你能做什么", "功能", "你会干啥"],
             "我可以帮您做以下事情：\n"
             "1. 🏠 控制智能家居设备\n"
             "2. 🌤 查询天气预报\n"
             "3. 📅 管理日程和提醒\n"
             "4. 🎵 播放音乐\n"
             "5. 💬 闲聊和回答问题"),
            (["再见", "拜拜", "bye", "goodbye", "下次见"],
             "好的，再见！期待下次为您服务。"),
            (["你是谁", "你叫什么"],
             '我是AI语音助手，您可以叫我"小爱同学"。'),
        ]

        for keywords, reply in rules:
            if any(kw in text for kw in keywords):
                return reply
        return None

    async def _call_llm(self, text: str, context: ConversationContext) -> str:
        """
        调用大模型 API（OpenAI 兼容接口）生成回复

        自动适配：
          - 有 API Key → 使用远程 LLM（如 OpenAI、DeepSeek）
          - 无 API Key → 自动切换到本地大模型（如 Ollama）
          本地模型不需要 Authorization header

        【优化】
          - 连接池复用：使用全局 httpx 客户端，避免每次创建新连接（节省 TCP 握手时间）
          - 响应缓存：相同问题在 TTL 内直接返回缓存结果（减少 API 调用）
          - 更短的超时：connect=5s, read=15s，快速降级
        """
        # ---- 尝试缓存 ----
        history_text = context.get_history_text(max_turns=2)  # 只用最近 2 轮判断相似性
        cached = _llm_cache.get(text, history_text)
        if cached:
            return cached

        messages = self._build_llm_messages(context)

        # 使用 Dialog 配置的 Provider（支持运行时热切换）
        dialog_provider_name = runtime_config.dialog_provider_name
        provider = provider_registry.get(dialog_provider_name) or provider_registry.get_default()
        api_base = provider.api_base if provider else ""
        model = provider.model if provider else ""
        logger.debug(f"[Dialog-LLM] 使用 Provider: {provider.name if provider else 'None'} (model={model})")

        try:
            # 构建请求头：如果 Provider 配置了 API Key 则添加鉴权
            headers = {"Content-Type": "application/json"}
            api_key = provider.api_key if provider else ""
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # 使用共享 httpx 客户端（连接池复用）
            resp = await get_http_client().post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": settings.OPENAI_MAX_TOKENS,
                    "temperature": settings.OPENAI_TEMPERATURE,
                },
                timeout=httpx.Timeout(15.0, connect=5.0),
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"].strip()

            # 写入缓存
            _llm_cache.put(text, history_text, reply)

            return reply

        except httpx.TimeoutException:
            logger.warning("[Dialog-LLM] API 请求超时")
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[Dialog-LLM] HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
        except Exception as e:
            logger.warning(f"[Dialog-LLM] 异常: {e}")

        return self._fallback_reply(text, context)

    async def _call_llm_stream(
        self, text: str, context: ConversationContext
    ):
        """
        流式调用 LLM，yield 文本片段（delta）

        使用全局 httpx 客户端的 stream() 接收 SSE 流，
        解析 OpenAI 兼容格式的 chunk，实时输出文本片段。
        """
        messages = self._build_llm_messages(context)

        dialog_provider_name = runtime_config.dialog_provider_name
        provider = provider_registry.get(dialog_provider_name) or provider_registry.get_default()
        api_base = provider.api_base if provider else ""
        model = provider.model if provider else ""

        headers = {"Content-Type": "application/json"}
        api_key = provider.api_key if provider else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with get_http_client().stream(
                "POST",
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "max_tokens": settings.OPENAI_MAX_TOKENS,
                    "temperature": settings.OPENAI_TEMPERATURE,
                },
                timeout=httpx.Timeout(15.0, connect=5.0),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        continue

        except httpx.TimeoutException:
            logger.warning("[Dialog-LLM-Stream] API 请求超时")
            yield self._fallback_reply(text, context)
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[Dialog-LLM-Stream] HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
            yield self._fallback_reply(text, context)
        except Exception as e:
            logger.warning(f"[Dialog-LLM-Stream] 异常: {e}")
            yield self._fallback_reply(text, context)

    def _build_llm_messages(self, context: ConversationContext) -> List[Dict[str, str]]:
        """构建 LLM 请求的消息列表（system + 历史），供流式/非流式复用"""
        system_prompt = (
            '你是一个智能语音助手，名叫"小爱同学"。请用友好、亲切的语气回答用户问题。\n'
            "回复要求:\n"
            "- 简洁自然，控制在 100 字以内，适合语音播报\n"
            "- 不要使用 Markdown 格式\n"
            "- 基于对话上下文给出连贯的回答\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *context.get_history_messages(max_turns=10),
        ]

        # 使用 Dialog 配置的 Provider
        dialog_provider_name = runtime_config.dialog_provider_name
        provider = provider_registry.get(dialog_provider_name) or provider_registry.get_default()
        model = provider.model if provider else ""

        # ---- headroom-ai 上下文压缩（降低 Token 消耗） ----
        if HEADROOM_AVAILABLE and runtime_config.enable_headroom_compression and messages:
            try:
                # compress() 是同步操作，在线程池中运行避免阻塞事件循环
                result = _headroom_compress(messages, model=model)
                if result.tokens_saved > 0:
                    logger.info(
                        f"[headroom] 对话压缩: 节省 {result.tokens_saved} tokens "
                        f"(压缩率: {result.compression_ratio:.1%})"
                    )
                messages = result.messages
            except Exception as e:
                logger.warning(f"[headroom] 对话压缩异常(已跳过): {e}")

        return messages

    def _fallback_reply(self, text: str, context: ConversationContext) -> str:
        """LLM 不可用时的兜底回复（基于上下文模板）"""
        # 如果能从历史中找到上一轮的主题，尝试关联
        if context.turn_count > 1:
            return (
                f"关于您刚才提到的，我理解了。不过我还需要更多信息才能准确回答。"
                f"请说得详细一些好吗？"
            )
        return f"收到您的消息。我还在学习中，暂时无法完美回答这个问题。"

    # ============================================================
    # 上下文辅助
    # ============================================================

    @staticmethod
    def _extract_city_from_history(context: ConversationContext) -> str:
        """从历史对话中提取最近提到的城市"""
        for msg in reversed(context.history):
            content = msg["content"]
            import re
            match = re.search(
                r"北京|上海|广州|深圳|杭州|成都|武汉|南京|天津|重庆|"
                r"苏州|西安|长沙|青岛|厦门",
                content,
            )
            if match:
                return match.group(0)
        return ""

    def _get_or_create(self, conversation_id: Optional[str]) -> ConversationContext:
        """获取会话，不存在则创建"""
        if conversation_id and conversation_id in self.conversations:
            return self.conversations[conversation_id]
        conv_id = conversation_id or str(uuid.uuid4())
        ctx = ConversationContext(session_id=conv_id)
        self.conversations[conv_id] = ctx
        return ctx

    # ============================================================
    # 回复构建
    # ============================================================

    @staticmethod
    def _build_response(
        conversation_id: str,
        response: str,
        intent: str,
        confidence: float,
        entities: Dict[str, Any],
        turn_count: int = 0,
        state: str = "idle",
        agent_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """构建统一格式的回复"""
        result = {
            "conversation_id": conversation_id,
            "response": response,
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "turn_count": turn_count,
            "state": state,
        }
        if agent_info:
            result["agent"] = agent_info
        return result

    # ============================================================
    # 会话管理
    # ============================================================

    def cleanup_expired(self) -> int:
        """清理所有超时会话（超过 30 分钟无活动）

        返回被清理的会话数量。
        建议在后台定时任务中调用（如每 5 分钟一次）。
        """
        expired_ids = [
            cid for cid, ctx in self.conversations.items()
            if ctx.is_expired()
        ]
        for cid in expired_ids:
            del self.conversations[cid]
            logger.info(f"[Dialog] 清理超时会话: {cid}")
        return len(expired_ids)

    def clear_conversation(self, conversation_id: str):
        """清除指定会话"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            logger.info(f"[Dialog] 清除会话: {conversation_id}")

    @property
    def active_count(self) -> int:
        """当前活跃会话数"""
        return len(self.conversations)

    @property
    def expired_count(self) -> int:
        """超时会话数"""
        return sum(1 for ctx in self.conversations.values() if ctx.is_expired())
