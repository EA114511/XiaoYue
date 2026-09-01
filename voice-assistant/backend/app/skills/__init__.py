"""
技能系统 (Skill System)

===== 架构设计 =====

Skill 是可插拔的能力模块，每个 Skill 包含一组 OpenAI Function Calling 描述
和对应的处理函数。智能体可以装配多个 Skill，在 LLM 调用时通过 Function Calling
让 LLM 自主决定何时调用哪个 Skill。

角色分层:
  - SkillDefinition: 技能定义（名称、描述、函数列表、处理器映射）
  - SkillRegistry: 技能注册中心（全局管理所有可用技能）
  - AgentConfig.equipped_skills: 智能体装配的技能名称列表
  - AgentOrchestrator._call_agent(): 注入装配的 Skill 到 LLM 调用

与 FunctionRegistry 的关系:
  Skill 系统是 FunctionRegistry 的上层抽象。一个 Skill 可以包含多个函数，
  并且通过 Function Calling 的方式让 LLM 自主调用，而非硬编码路由。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("voice-assistant.skills")

# ============================================================
# 类型定义
# ============================================================

# Skill 处理函数签名: async (params: dict) -> str
SkillHandler = Callable[[Dict[str, Any]], str]

# OpenAI Function Calling Schema 格式
SkillFunctionSchema = Dict[str, Any]


@dataclass
class SkillFunction:
    """
    Skill 中的一个可调用函数

    对应 OpenAI Function Calling 中的一个 tool/function:
      - name: 函数名（LLM 调用时使用的标识）
      - description: 函数描述（LLM 理解函数用途）
      - handler: 实际执行函数
      - parameters: JSON Schema 格式的参数描述
    """
    name: str
    description: str
    handler: SkillHandler
    parameters: Dict[str, Any]


@dataclass
class SkillDefinition:
    """
    技能定义

    一个技能是一个可插拔的能力模块，包含:
      - name: 技能唯一标识（如 "web_search"）
      - display_name: 显示名称（如 "联网搜索"）
      - description: 技能描述（用于展示和筛选）
      - functions: 技能包含的可调用函数列表
      - category: 技能分类（如 "工具"、"数据"、"娱乐"）
      - enabled: 是否启用
    """
    name: str
    display_name: str
    description: str
    functions: List[SkillFunction] = field(default_factory=list)
    category: str = "通用"
    enabled: bool = True

    def to_function_calling_schemas(self) -> List[SkillFunctionSchema]:
        """
        将 Skill 中的所有函数转换为 OpenAI Function Calling 格式的 schema 列表

        用于注入 LLM 调用的 tools 参数。
        """
        schemas = []
        for func in self.functions:
            schemas.append({
                "type": "function",
                "function": {
                    "name": func.name,
                    "description": func.description,
                    "parameters": func.parameters,
                },
            })
        return schemas

    def get_handler(self, function_name: str) -> Optional[SkillHandler]:
        """根据函数名获取对应的处理函数"""
        for func in self.functions:
            if func.name == function_name:
                return func.handler
        return None

    def has_function(self, function_name: str) -> bool:
        """检查是否包含指定函数"""
        return any(func.name == function_name for func in self.functions)

    def add_function(self, func: SkillFunction):
        """添加一个函数到技能中"""
        # 检查同名函数是否已存在
        for i, f in enumerate(self.functions):
            if f.name == func.name:
                self.functions[i] = func
                logger.info(f"[Skill] 更新函数 '{func.name}' 在技能 '{self.name}' 中")
                return
        self.functions.append(func)
        logger.info(f"[Skill] 添加函数 '{func.name}' 到技能 '{self.name}'")


# ============================================================
# 技能注册中心
# ============================================================

class SkillRegistry:
    """
    技能注册中心 — 管理所有可用技能

    职责:
      1. 注册/注销技能
      2. 查询可用技能
      3. 调用技能函数
      4. 为指定智能体提供 Function Calling schemas
    """

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}

    # ============================================================
    # 注册管理
    # ============================================================

    def register(self, skill: SkillDefinition) -> bool:
        """
        注册一个技能

        返回:
            True 表示注册成功，False 表示已存在相同名称的技能
        """
        if skill.name in self._skills:
            logger.warning(f"[SkillRegistry] 技能 '{skill.name}' 已存在，将被覆盖")
        self._skills[skill.name] = skill
        logger.info(
            f"[SkillRegistry] 注册技能: '{skill.name}' "
            f"(分类={skill.category}, 函数数={len(skill.functions)})"
        )
        return True

    def unregister(self, skill_name: str) -> bool:
        """
        注销一个技能

        返回:
            True 表示成功注销，False 表示技能不存在
        """
        if skill_name not in self._skills:
            logger.warning(f"[SkillRegistry] 技能 '{skill_name}' 不存在，无法注销")
            return False
        del self._skills[skill_name]
        logger.info(f"[SkillRegistry] 注销技能: '{skill_name}'")
        return True

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """获取指定技能"""
        return self._skills.get(name)

    def get_all_skills(self) -> Dict[str, SkillDefinition]:
        """获取所有已注册的技能（只读视图）"""
        return dict(self._skills)

    def get_skills_by_category(self, category: str) -> Dict[str, SkillDefinition]:
        """按分类获取技能"""
        return {
            name: skill
            for name, skill in self._skills.items()
            if skill.category == category
        }

    def get_enabled_skills(self) -> Dict[str, SkillDefinition]:
        """获取所有已启用的技能"""
        return {
            name: skill
            for name, skill in self._skills.items()
            if skill.enabled
        }

    def skill_exists(self, name: str) -> bool:
        """检查技能是否已注册"""
        return name in self._skills

    # ============================================================
    # 技能调用
    # ============================================================

    async def call_skill_function(
        self,
        skill_name: str,
        function_name: str,
        params: Dict[str, Any],
    ) -> str:
        """
        调用指定技能的指定函数

        参数:
            skill_name: 技能名称
            function_name: 函数名称
            params: 函数参数

        返回:
            适合语音播报的回复文本

        异常:
            ValueError: 技能或函数不存在
        """
        skill = self._skills.get(skill_name)
        if not skill:
            raise ValueError(f"技能 '{skill_name}' 不存在")

        handler = skill.get_handler(function_name)
        if not handler:
            raise ValueError(
                f"技能 '{skill_name}' 中不存在函数 '{function_name}'"
            )

        logger.info(
            f"[SkillRegistry] 调用: skill={skill_name}, "
            f"function={function_name}, params={params}"
        )
        try:
            result = await handler(params)
            logger.info(
                f"[SkillRegistry] 调用成功: skill={skill_name}, "
                f"function={function_name}, result=\"{str(result)[:60]}...\""
            )
            return result
        except Exception as e:
            logger.error(
                f"[SkillRegistry] 调用异常: skill={skill_name}, "
                f"function={function_name}, error={e}"
            )
            raise

    # ============================================================
    # 智能体装配相关
    # ============================================================

    def get_agent_tools(
        self,
        equipped_skills: List[str],
    ) -> List[SkillFunctionSchema]:
        """
        获取智能体装配的所有技能的 Function Calling schemas

        参数:
            equipped_skills: 智能体装配的技能名称列表

        返回:
            OpenAI Function Calling 格式的 tool schemas 列表
        """
        tools = []
        for skill_name in equipped_skills:
            skill = self._skills.get(skill_name)
            if skill and skill.enabled:
                tools.extend(skill.to_function_calling_schemas())
        return tools

    def get_agent_function_handlers(
        self,
        equipped_skills: List[str],
    ) -> Dict[str, tuple]:
        """
        获取智能体装配的所有技能的函数名 → (skill_name, handler) 映射

        用于 LLM 返回 function_call 后进行路由执行。
        """
        handlers = {}
        for skill_name in equipped_skills:
            skill = self._skills.get(skill_name)
            if skill and skill.enabled:
                for func in skill.functions:
                    handlers[func.name] = (skill_name, func.handler)
        return handlers


# ============================================================
# 全局单例
# ============================================================

# 全局技能注册中心
skill_registry = SkillRegistry()
