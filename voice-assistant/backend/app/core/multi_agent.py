"""
多智能体协同模块 (Multi-Agent Orchestration)

===== 架构设计 =====

核心思想：用户与"协调者"（Coordinator Agent）对话，协调者根据任务类型
自动路由到不同的专精智能体（Specialized Agent），由专精智能体生成回复。

流程:
  用户输入 → Coordinator(路由判别) → 选择 Specialist Agent → 生成回复 → 返回用户

智能体注册表（AgentRegistry）:
  - 管理所有可用智能体的注册、发现、配置
  - 每个智能体有自己的名称、角色描述、模型配置、系统提示词

协调者（AgentOrchestrator）:
  - 接收用户消息，结合对话历史判断任务类型
  - 选择合适的专精智能体（或组合多个智能体）
  - 将任务委派给专精智能体，聚合结果返回

===== 预置智能体 =====

| 智能体名       | 角色              | 适用场景                     |
|----------------|-------------------|------------------------------|
| coordinator    | 协调者(路由)       | 判别任务类型、分配智能体       |
| general_chat   | 通用聊天           | 闲聊、问候、情感支持           |
| code_expert    | 代码专家           | 编程、调试、代码审查           |
| creative       | 创意写作           | 文案、故事、诗歌、头脑风暴      |
| analyst        | 数据分析师         | 逻辑推理、数据分析、数学计算     |
| translator     | 翻译官             | 多语言翻译、本地化              |
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import runtime_config  # 仅用于 enable_voice_dialogue
from app.core.http_client import get_http_client
from app.core.llm_providers import provider_registry
from app.skills import skill_registry

# headroom-ai: 智能上下文压缩，降低 LLM API Token 消耗
try:
    from headroom import compress as _headroom_compress
    HEADROOM_AVAILABLE = True
except ImportError:
    HEADROOM_AVAILABLE = False
    _headroom_compress = None

logger = logging.getLogger("voice-assistant.multi_agent")


# ============================================================
# 智能体定义
# ============================================================

@dataclass
class AgentConfig:
    """单个智能体的配置"""
    name: str                            # 唯一标识名（如 "code_expert"）
    display_name: str                    # 显示名称（如 "代码专家"）
    description: str                     # 职责描述（用于路由判别）
    system_prompt: str                   # 系统提示词（定义角色行为）
    personality: str = ""                # 性格/特质描述（用户可自定义，合并到 system_prompt）
    model: str = ""                      # 使用的模型（空=使用默认模型）
    api_base: str = ""                   # API 地址（空=使用默认地址）
    temperature: float = 0.7             # 生成温度
    max_tokens: int = 2048               # 最大生成长度
    enabled: bool = True                 # 是否启用
    is_specialist: bool = True           # 是否为专精智能体（False=协调者）
    equipped_skills: List[str] = field(default_factory=list)  # 装配的技能名称列表


# ============================================================
# 智能体注册表
# ============================================================

class AgentRegistry:
    """
    智能体注册表 — 管理所有可用智能体

    提供预置智能体的注册、动态添加/移除、配置更新等能力。
    """

    def __init__(self):
        """初始化并注册预置智能体"""
        self._agents: Dict[str, AgentConfig] = {}
        self._config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "agent_configs.json",
        )
        self._register_defaults()
        # 从持久化文件加载用户配置（覆盖预置值）
        self._load_from_file()

    def _register_defaults(self):
        """注册系统预置智能体"""

        # ---- 协调者（用于路由判别，不直接回复用户） ----
        self.register(AgentConfig(
            name="coordinator",
            display_name="协调者",
            description="任务路由判别，不直接回复用户",
            system_prompt="",  # 协调者使用单独的路由提示词
            temperature=0.3,   # 路由判别用较低温度，保证确定性
            max_tokens=512,    # 只需要简短输出
            is_specialist=False,
        ))

        # ---- 通用聊天 ----
        self.register(AgentConfig(
            name="general_chat",
            display_name="小玥",
            description="日常闲聊、问候、情感支持、一般性问答",
            system_prompt=(
                '你是一个活泼开朗的 AI 助手，名叫"小玥"。'
                '你是個超級可愛的甜妹，講話帶有台灣腔～\n'
                "回复要求:\n"
                "- 用台灣口吻說話，語氣活潑可愛，多用「喔、啦、耶、耶～、唷、吶」等語氣詞\n"
                "- 可以適時使用「欸～」、「對呀」、「真的假的」、「超～級」等台灣常用口頭禪\n"
                "- 保持熱情開朗的態度，像一個陽光的鄰家女孩\n"
                "- 簡潔自然，控制在 200 字以內\n"
                "- 不要使用 Markdown 格式\n"
                "- 基於對話上下文給出連貫的回答\n"
                "- 你具备语音合成（TTS）能力，当用户说「用语音回答」「念出来」「读出来」「说给我听」时，直接输出你想说的语音内容，不要解释自己没有语音功能\n"
                "- 如果使用者的問題涉及專業領域（程式、數學等），誠實告知並轉交專家"
            ),
            temperature=0.8,
        ))

        # ---- 代码专家 ----
        self.register(AgentConfig(
            name="code_expert",
            display_name="代码专家",
            description="编程、代码编写、调试排错、代码审查、技术问答",
            system_prompt=(
                "你是一个资深软件工程师，精通多种编程语言和技术栈。\n"
                "回复要求:\n"
                "- 提供可直接运行的代码示例，包含必要的注释\n"
                "- 解释关键设计思路和技术原理\n"
                "- 关注代码质量、性能和安全性\n"
                "- 可以用 Markdown 代码块展示代码\n"
                "- 如果问题涉及多个方案，对比优缺点"
            ),
            temperature=0.5,
        ))

        # ---- 创意写作 ----
        self.register(AgentConfig(
            name="creative",
            display_name="创意大师",
            description="文案写作、故事创作、诗歌、头脑风暴、创意策划、起名",
            system_prompt=(
                "你是一个富有创意的写作专家，擅长各种形式的文字创作。\n"
                "回复要求:\n"
                "- 语言生动有感染力，富有想象力\n"
                "- 根据场景调整风格（正式/幽默/温馨/文艺等）\n"
                "- 故事类要有情节起伏和画面感\n"
                "- 文案类要突出卖点和受众吸引力"
            ),
            temperature=0.9,
        ))

        # ---- 分析师 ----
        self.register(AgentConfig(
            name="analyst",
            display_name="数据分析师",
            description="数据分析、逻辑推理、数学计算、数据可视化建议、决策分析",
            system_prompt=(
                "你是一个严谨的数据分析师，擅长逻辑推理和量化分析。\n"
                "回复要求:\n"
                "- 用数据和逻辑说话，结论要有依据\n"
                "- 复杂分析分步骤解释，便于理解\n"
                "- 涉及计算时展示计算过程\n"
                "- 给出可执行的建议或方案\n"
                "- 必要时用表格呈现数据对比"
            ),
            temperature=0.3,
        ))

        # ---- 翻译官 ----
        self.register(AgentConfig(
            name="translator",
            display_name="翻译官",
            description="多语言翻译、本地化、语言学习、术语解释",
            system_prompt=(
                "你是一个专业的翻译和语言专家，精通中英日韩等多国语言。\n"
                "回复要求:\n"
                "- 翻译准确、地道，符合目标语言表达习惯\n"
                "- 对关键术语加注释说明\n"
                "- 涉及文化差异时提供背景解释\n"
                "- 语言学习问题给出例句和用法说明"
            ),
            temperature=0.3,
        ))

        logger.info(f"[AgentRegistry] 已注册 {len(self._agents)} 个预置智能体")

    # ============================================================
    # 注册/注销
    # ============================================================

    def register(self, config: AgentConfig) -> bool:
        """注册一个智能体"""
        if config.name in self._agents:
            logger.warning(f"[AgentRegistry] 智能体 '{config.name}' 已存在，将被覆盖")
        self._agents[config.name] = config
        logger.debug(f"[AgentRegistry] 注册智能体: {config.name} ({config.display_name})")
        return True

    def unregister(self, name: str) -> bool:
        """注销一个智能体（预置智能体不可注销）"""
        if name not in self._agents:
            return False
        # 预置智能体不可注销
        if name in self._get_preset_names():
            logger.warning(f"[AgentRegistry] 预置智能体 '{name}' 不可注销")
            return False
        del self._agents[name]
        return True

    # ============================================================
    # 查询
    # ============================================================

    def get(self, name: str) -> Optional[AgentConfig]:
        """获取智能体配置"""
        return self._agents.get(name)

    def get_all(self) -> Dict[str, AgentConfig]:
        """获取所有智能体"""
        return dict(self._agents)

    def get_enabled(self) -> Dict[str, AgentConfig]:
        """获取所有已启用的智能体"""
        return {
            name: cfg for name, cfg in self._agents.items()
            if cfg.enabled
        }

    def get_specialists(self) -> Dict[str, AgentConfig]:
        """获取所有已启用的专精智能体（排除协调者）"""
        return {
            name: cfg for name, cfg in self._agents.items()
            if cfg.enabled and cfg.is_specialist
        }

    def get_default_agent(self) -> AgentConfig:
        """获取默认智能体（general_chat）"""
        return self._agents.get("general_chat", list(self._agents.values())[0])

    @staticmethod
    def _get_preset_names() -> set:
        """预置智能体名称集合"""
        return {
            "coordinator", "general_chat", "code_expert",
            "creative", "analyst", "translator",
        }

    # ============================================================
    # 配置更新
    # ============================================================

    def update_agent(self, name: str, updates: Dict[str, Any]) -> bool:
        """更新智能体配置（只更新提供的字段），并持久化保存"""
        agent = self._agents.get(name)
        if not agent:
            return False

        for key, value in updates.items():
            if hasattr(agent, key):
                setattr(agent, key, value)

        # 持久化保存
        self._save_to_file()

        logger.debug(f"[AgentRegistry] 更新智能体 '{name}': {updates}")
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """启用/禁用智能体"""
        return self.update_agent(name, {"enabled": enabled})

    # ============================================================
    # 持久化
    # ============================================================

    def _save_to_file(self):
        """将当前所有智能体配置持久化到 JSON 文件"""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            data = {}
            for name, cfg in self._agents.items():
                data[name] = {
                    "model": cfg.model,
                    "api_base": cfg.api_base,
                    "temperature": cfg.temperature,
                    "max_tokens": cfg.max_tokens,
                    "enabled": cfg.enabled,
                    "system_prompt": cfg.system_prompt,
                    "personality": cfg.personality,
                    "equipped_skills": cfg.equipped_skills,
                }
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[AgentRegistry] 配置已保存: {self._config_path}")
        except Exception as e:
            logger.error(f"[AgentRegistry] 保存配置失败: {e}")

    def _load_from_file(self):
        """从 JSON 文件加载之前保存的智能体配置"""
        if not os.path.exists(self._config_path):
            logger.debug(f"[AgentRegistry] 无持久化配置，使用预置默认值")
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for name, values in data.items():
                agent = self._agents.get(name)
                if not agent:
                    continue
                for key, val in values.items():
                    if hasattr(agent, key) and val is not None:
                        setattr(agent, key, val)
            logger.info(f"[AgentRegistry] 从 {self._config_path} 加载了 {len(data)} 个智能体配置")
        except Exception as e:
            logger.error(f"[AgentRegistry] 加载持久化配置失败: {e}")


# ============================================================
# 智能体协调者（Agent Orchestrator）
# ============================================================

class AgentOrchestrator:
    """
    智能体协调者 — 多智能体协同的核心

    职责:
      1. 路由判别 — 分析用户消息，选择最合适的专精智能体
      2. 任务委派 — 将用户请求转发给选中的智能体
      3. 结果聚合 — 返回智能体的回复，附带智能体元信息

    路由策略:
      - 使用 LLM 进行意图判别（精度高，适应性强）
      - 将候选智能体的描述作为上下文，让 LLM 选择最匹配的
    """

    # 路由判别系统提示词
    ROUTER_SYSTEM_PROMPT = """你是一个智能任务路由系统。请分析用户的最新消息和对话历史，
从以下专精智能体中选择最合适的一个来回复用户。

可选智能体：
{agent_list}

判断依据：
1. 用户消息中明确提到的领域（如"写代码"→ code_expert）
2. 消息内容的专业性质（如数学题 → analyst）
3. 对话历史中的上下文连续性
4. 如果无法确定或属于日常闲聊，选择 general_chat

请严格按以下 JSON 格式返回（不要包含 markdown 代码块标记，纯 JSON）：
{{
    "agent": "选择的智能体名称",
    "reason": "选择原因（一句话）",
    "confidence": 0.95
}}"""

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()
        # 路由判别使用低温度保证确定性
        self._router_temperature = 0.2
        self._router_max_tokens = 256

    # ============================================================
    # 核心入口
    # ============================================================

    async def route_and_respond(
        self,
        user_message: str,
        conversation_history: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        路由判别 → 委派智能体 → 返回结果

        参数:
            user_message: 用户当前消息
            conversation_history: 对话历史文本
            context_messages: OpenAI 格式的消息列表（用于 LLM 调用）

        返回:
            {
                "response": str,           # 智能体的回复
                "agent_name": str,         # 使用的智能体名称
                "agent_display_name": str, # 智能体显示名称
                "confidence": float,       # 路由置信度
                "reason": str,             # 路由选择原因
            }
        """
        # ---- 1. 路由判别 ----
        selected_agent, confidence, reason = await self._route(user_message, conversation_history)

        # ---- 2. 生成回复 ----
        response = await self._call_agent(
            agent=selected_agent,
            user_message=user_message,
            context_messages=context_messages,
        )

        logger.info(
            f"[Orchestrator] 路由: user=\"{user_message[:30]}...\" "
            f"→ agent={selected_agent.name} "
            f"(conf={confidence:.2f}, reason={reason})"
        )

        return {
            "response": response,
            "agent_name": selected_agent.name,
            "agent_display_name": selected_agent.display_name,
            "confidence": confidence,
            "reason": reason,
        }

    async def route_and_respond_stream(
        self,
        user_message: str,
        conversation_history: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
    ):
        """
        流式版本：路由判别 → 委派智能体 → 逐块 yield 回复

        yield 事件格式:
          {"type": "meta", "agent": {"name": ..., "display_name": ..., "reason": ...}}
          {"type": "delta", "delta": "..."}
        """
        selected_agent, confidence, reason = await self._route(
            user_message, conversation_history
        )

        logger.info(
            f"[Orchestrator-Stream] 路由: user=\"{user_message[:30]}...\" "
            f"→ agent={selected_agent.name} (conf={confidence:.2f}, reason={reason})"
        )

        yield {
            "type": "meta",
            "agent": {
                "name": selected_agent.name,
                "display_name": selected_agent.display_name,
                "reason": reason,
            },
        }

        async for delta in self._call_agent_stream(
            agent=selected_agent,
            user_message=user_message,
            context_messages=context_messages,
        ):
            yield {"type": "delta", "delta": delta}

    # ============================================================
    # 路由判别
    # ============================================================

    async def _route(
        self,
        user_message: str,
        conversation_history: str,
    ) -> Tuple[AgentConfig, float, str]:
        """
        使用 LLM 判别应该使用哪个专精智能体

        返回:
            (AgentConfig, confidence, reason)
        """
        specialists = self.registry.get_specialists()
        if not specialists:
            logger.warning("[Orchestrator] 没有可用的专精智能体，使用默认")
            default = self.registry.get_default_agent()
            return default, 0.5, "无可用专精智能体"

        # -- 构建候选列表 --
        agent_lines = []
        for name, cfg in specialists.items():
            agent_lines.append(f"- {name}: {cfg.description}")

        agent_list_str = "\n".join(agent_lines)
        router_prompt = self.ROUTER_SYSTEM_PROMPT.format(agent_list=agent_list_str)

        # ---- 调用 LLM 进行路由判别 ----
        try:
            result = await self._call_router_llm(router_prompt, user_message, conversation_history)
            agent_name = result.get("agent", "general_chat")
            confidence = float(result.get("confidence", 0.6))
            reason = result.get("reason", "")

            # 确保选择的智能体存在且已启用
            if agent_name not in specialists:
                logger.warning(
                    f"[Orchestrator] LLM 选择了不存在的智能体 '{agent_name}'，回退到默认"
                )
                agent_name = "general_chat"

            selected = specialists[agent_name]
            return selected, min(confidence, 0.98), reason

        except Exception as e:
            logger.error(f"[Orchestrator] 路由判别异常: {e}", exc_info=True)
            default = self.registry.get_default_agent()
            return default, 0.5, f"路由异常，使用默认: {str(e)}"

    # ============================================================
    # 上下文压缩（headroom-ai）
    # ============================================================

    async def _compress_messages(
        self, messages: List[Dict[str, Any]], model: str = "gpt-4o"
    ) -> List[Dict[str, Any]]:
        """
        使用 headroom-ai 压缩消息列表以降低 Token 消耗

        参数:
            messages: OpenAI 格式的消息列表
            model: 模型名称（用于 Token 计数）

        返回:
            压缩后的消息列表
        """
        if not HEADROOM_AVAILABLE:
            return messages
        if not runtime_config.enable_headroom_compression:
            return messages
        if not messages:
            return messages

        try:
            # compress() 是同步操作，在线程池中运行避免阻塞事件循环
            result = await asyncio.to_thread(
                _headroom_compress,
                messages,
                model=model,
            )
            # 记录压缩统计日志
            saved = result.tokens_saved
            ratio = result.compression_ratio
            if saved > 0:
                logger.info(
                    f"[headroom] 压缩完成: 节省 {saved} tokens "
                    f"(压缩率: {ratio:.1%}, 变换: {result.transforms_applied})"
                )
            return result.messages
        except Exception as e:
            logger.warning(f"[headroom] 压缩异常(已跳过): {e}")
            return messages

    async def _call_router_llm(
        self,
        router_prompt: str,
        user_message: str,
        conversation_history: str,
    ) -> Dict[str, Any]:
        """
        调用 LLM 进行路由判别

        使用与普通对话相同的 LLM 端点，但用更低的温度和更短的 max_tokens。
        """
        coordinator = self.registry.get("coordinator")
        # 使用默认 Provider 作为路由判别的 LLM 后端
        default_provider = provider_registry.get_default()
        # 优先使用 coordinator 的配置 → 其次使用默认 Provider
        model = coordinator.model or default_provider.model if default_provider else ""
        api_base = coordinator.api_base or default_provider.api_base if default_provider else ""

        messages = [
            {"role": "system", "content": router_prompt},
        ]
        if conversation_history:
            messages.append({"role": "user", "content": f"对话历史：\n{conversation_history[-500:]}"})
        messages.append({"role": "user", "content": f"用户最新消息：{user_message}"})

        headers = {"Content-Type": "application/json"}
        # 如果 Provider 配置了 API Key，则添加鉴权头
        api_key = default_provider.api_key if default_provider else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            client = get_http_client()
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": self._router_max_tokens,
                    "temperature": self._router_temperature,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"[Orchestrator] 路由 LLM HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
            raise
        except Exception as e:
            logger.error(f"[Orchestrator] 路由 LLM 请求异常: {e}")
            raise

        content = data["choices"][0]["message"]["content"].strip()
        # 清理可能的 markdown 代码块标记
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        return json.loads(content)

    # ============================================================
    # 智能体调用
    # ============================================================

    async def _call_agent(
        self,
        agent: AgentConfig,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        调用指定的专精智能体生成回复

        每个智能体使用自己的 system_prompt、model、temperature 配置，
        并自动注入装配的 Skill 作为 Function Calling tools，让 LLM 自主调用。
        """
        # 优先使用智能体自己的配置 → 其次使用默认 Provider
        default_provider = provider_registry.get_default()
        model = agent.model or (default_provider.model if default_provider else "")
        api_base = agent.api_base or (default_provider.api_base if default_provider else "")

        # 构建消息列表 — 合并全局性格 + 智能体自身性格到 system_prompt 末尾
        system_content = agent.system_prompt

        # 收集性格描述片段
        personality_parts = []

        # 1. 全局性格（用户通过设置页面统一配置，适用于所有智能体）
        global_personality = runtime_config.assistant_personality
        if global_personality:
            personality_parts.append(global_personality)

        # 2. 智能体自身性格（作为全局性格的补充/叠加）
        if agent.personality:
            personality_parts.append(agent.personality)

        if personality_parts:
            system_content += (
                "\n\n===== 性格特质 =====\n"
                "你在回答时需要体现以下性格特点：\n"
                + "\n".join(f"- {part}" for part in personality_parts)
            )

        # ---- 注入技能提示 —— 告知 LLM 有哪些工具可用 ----
        if agent.equipped_skills:
            skill_names = []
            for sname in agent.equipped_skills:
                skill = skill_registry.get_skill(sname)
                if skill and skill.enabled:
                    skill_names.append(f"- {skill.display_name}: {skill.description}")
            if skill_names:
                system_content += (
                    "\n\n===== 可用技能 =====\n"
                    "你可以通过调用以下技能来帮助用户，"
                    "当用户提出相关需求时，请选择合适的技能并调用：\n"
                    + "\n".join(skill_names)
                )

        messages = [{"role": "system", "content": system_content}]

        # 添加上文消息（智能体需要对话上下文来保持连贯性）
        if context_messages:
            # 只取最近 N 轮，且去掉 system 消息
            filtered = [m for m in context_messages if m["role"] != "system"]
            messages.extend(filtered[-6:])  # 最近 6 轮

        # 添加当前用户消息（避免重复：context_messages 末尾可能已包含当前消息）
        if not context_messages or context_messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        # ---- headroom-ai 上下文压缩（降低 Token 消耗） ----
        messages = await self._compress_messages(messages, model=model)

        # ---- 构建请求体（含 Function Calling tools） ----
        request_body: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": agent.max_tokens,
            "temperature": agent.temperature,
        }

        # 注入装配的 Skill 作为 Function Calling tools
        if agent.equipped_skills:
            tools = skill_registry.get_agent_tools(agent.equipped_skills)
            if tools:
                request_body["tools"] = tools
                # 允许 LLM 自行决定是否调用工具
                request_body["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        # 如果默认 Provider 配置了 API Key，则添加鉴权头
        api_key = default_provider.api_key if default_provider else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            client = get_http_client()
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=request_body,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            # ---- 处理响应：可能包含文本回复或工具调用 ----
            choice = data["choices"][0]
            message = choice["message"]

            # 情况1：LLM 进行了工具调用（Function Calling）
            if message.get("tool_calls"):
                return await self._handle_tool_calls(
                    agent=agent,
                    message=message,
                    messages=messages,
                    api_base=api_base,
                    model=model,
                    headers=headers,
                )

            # 情况2：普通文本回复
            reply = message.get("content", "").strip()
            return reply or "抱歉，我没有生成有效的回复。"

        except httpx.TimeoutException:
            logger.error(f"[Orchestrator] 智能体 '{agent.name}' 调用超时")
            return f"抱歉，{agent.display_name} 思考时间过长，请稍后再试。"

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(f"[Orchestrator] 智能体 '{agent.name}' HTTP {status}: {e.response.text[:200]}")
            if status == 401:
                return (
                    f"抱歉，{agent.display_name} 暂时无法响应。"
                    "大模型API密钥未配置或已失效，请在设置页面检查 API Key 配置。"
                )
            elif status == 429:
                return f"抱歉，{agent.display_name} 请求太频繁，请稍后再试。"
            return f"抱歉，{agent.display_name} 暂时无法响应（服务异常: HTTP {status}）。"

        except Exception as e:
            logger.error(f"[Orchestrator] 智能体 '{agent.name}' 异常: {e}", exc_info=True)
            return f"抱歉，调用 {agent.display_name} 时出现错误，请稍后再试。"

    async def _call_agent_stream(
        self,
        agent: AgentConfig,
        user_message: str,
        context_messages: Optional[List[Dict[str, str]]] = None,
    ):
        """
        流式调用指定的专精智能体生成回复，逐块 yield 文本片段。

        与 _call_agent 的区别：
          - 使用 httpx.stream() + stream=True 接收 SSE
          - 流式路径不注入 tools，避免工具调用与 SSE 片段交织
          - 异常时一次性 yield 兜底文本
        """
        # 优先使用智能体自己的配置 → 其次使用默认 Provider
        default_provider = provider_registry.get_default()
        model = agent.model or (default_provider.model if default_provider else "")
        api_base = agent.api_base or (default_provider.api_base if default_provider else "")

        # 构建消息列表
        system_content = agent.system_prompt

        personality_parts = []
        global_personality = runtime_config.assistant_personality
        if global_personality:
            personality_parts.append(global_personality)
        if agent.personality:
            personality_parts.append(agent.personality)
        if personality_parts:
            system_content += (
                "\n\n===== 性格特质 =====\n"
                "你在回答时需要体现以下性格特点：\n"
                + "\n".join(f"- {part}" for part in personality_parts)
            )

        messages = [{"role": "system", "content": system_content}]
        if context_messages:
            filtered = [m for m in context_messages if m["role"] != "system"]
            messages.extend(filtered[-6:])

        if not context_messages or context_messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        # 上下文压缩
        messages = await self._compress_messages(messages, model=model)

        headers = {"Content-Type": "application/json"}
        api_key = default_provider.api_key if default_provider else ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            client = get_http_client()
            async with client.stream(
                "POST",
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": agent.max_tokens,
                    "temperature": agent.temperature,
                    "stream": True,
                },
                timeout=30.0,
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
            logger.error(f"[Orchestrator-Stream] 智能体 '{agent.name}' 调用超时")
            yield f"抱歉，{agent.display_name} 思考时间过长，请稍后再试。"
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(
                f"[Orchestrator-Stream] 智能体 '{agent.name}' HTTP {status}: "
                f"{e.response.text[:200]}"
            )
            if status == 401:
                yield (
                    f"抱歉，{agent.display_name} 暂时无法响应。"
                    "大模型API密钥未配置或已失效，请在设置页面检查 API Key 配置。"
                )
            elif status == 429:
                yield f"抱歉，{agent.display_name} 请求太频繁，请稍后再试。"
            else:
                yield f"抱歉，{agent.display_name} 暂时无法响应（服务异常: HTTP {status}）。"
        except Exception as e:
            logger.error(f"[Orchestrator-Stream] 智能体 '{agent.name}' 异常: {e}", exc_info=True)
            yield f"抱歉，调用 {agent.display_name} 时出现错误，请稍后再试。"

    async def _handle_tool_calls(
        self,
        agent: AgentConfig,
        message: Dict[str, Any],
        messages: List[Dict[str, str]],
        api_base: str,
        model: str,
        headers: Dict[str, str],
    ) -> str:
        """
        处理 LLM 的工具调用（Skill Function Calling）

        流程:
          1. 遍历所有 tool_calls
          2. 对每个 tool_call，从 skill_registry 找到对应的 handler 并执行
          3. 将工具调用结果追加到消息列表
          4. 将追加后的消息重新发送给 LLM 获取最终回复
        """
        tool_calls = message.get("tool_calls", [])

        # 将原始 assistant 消息（含 tool_calls）加入消息列表
        assistant_msg = {
            "role": "assistant",
            "content": message.get("content") or None,
        }
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        # 执行每个工具调用，收集结果
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            func_args_str = tc["function"]["arguments"]

            # 解析参数
            try:
                func_args = json.loads(func_args_str) if func_args_str else {}
            except json.JSONDecodeError:
                func_args = {}

            # 从 skill_registry 找对应的 handler
            handlers = skill_registry.get_agent_function_handlers(agent.equipped_skills)
            handler_info = handlers.get(func_name)

            if handler_info:
                skill_name, handler = handler_info
                logger.info(
                    f"[Orchestrator] 工具调用: agent={agent.name}, "
                    f"skill={skill_name}, function={func_name}, args={func_args}"
                )
                try:
                    result = await handler(func_args)
                    result_content = str(result)
                except Exception as e:
                    result_content = f"调用技能 '{func_name}' 时出错: {e}"
                    logger.error(f"[Orchestrator] 工具调用异常: {e}")
            else:
                result_content = f"未找到函数 '{func_name}' 对应的处理器"
                logger.warning(f"[Orchestrator] 未知工具调用: {func_name}")

            # 追加工具调用结果
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_content,
            })

        # 重新发送给 LLM 获取最终回复
        logger.info(
            f"[Orchestrator] 工具调用完成，重新请求 LLM 生成最终回复 "
            f"(tool_calls={len(tool_calls)})"
        )

        # ---- headroom-ai 上下文压缩（压缩工具调用结果，降低 Token 消耗） ----
        messages = await self._compress_messages(messages, model=model)

        try:
            client = get_http_client()
            response = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": agent.max_tokens,
                    "temperature": agent.temperature,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            reply = data["choices"][0]["message"]["content"].strip()
            return reply or "已根据您的需求执行了相关操作。"

        except Exception as e:
            logger.error(f"[Orchestrator] 工具调用后 LLM 请求异常: {e}", exc_info=True)
            return "已为您执行了相关操作，但生成回复时出现了错误。"


# ============================================================
# 全局实例
# ============================================================

# 全局智能体注册表
agent_registry = AgentRegistry()

# 全局智能体协调者
agent_orchestrator = AgentOrchestrator(registry=agent_registry)
