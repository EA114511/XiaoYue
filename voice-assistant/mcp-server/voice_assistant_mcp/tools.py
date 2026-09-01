"""
MCP 工具函数 — 封装所有暴露给 MCP 客户端的操作

每个函数对应一个 MCP tool，遵循以下规范：
  - 函数名 = 工具名（snake_case）
  - 类型注解 = 输入参数 schema
  - 文档字符串 = 工具描述（LLM 用）
  - 返回值 = 字符串（Markdown 格式，适合 LLM 阅读）
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from voice_assistant_mcp.api_client import ApiClient

logger = logging.getLogger("voice-assistant-mcp.tools")


# ============================================================
# 格式化工具
# ============================================================

def _format_json(data: Any) -> str:
    """将数据格式化为美观的 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _format_provider(p: dict) -> str:
    """格式化单个 LLM Provider 为可读文本"""
    name = p.get("name", "?")
    model = p.get("model", "未配置") or "未配置"
    api_base = p.get("api_base", "未配置") or "未配置"
    key_status = "✅ 已配置" if p.get("api_key_configured") else "⚠️ 未配置"
    return (
        f"  • **{name}** — {model}\n"
        f"    API Base: `{api_base}`\n"
        f"    API Key: {key_status}"
    )


def _format_agent(a: dict) -> str:
    """格式化单个智能体为可读文本"""
    name = a.get("name", "?")
    display_name = a.get("display_name", name)
    description = a.get("description", "")
    enabled = "✅ 启用" if a.get("enabled") else "❌ 禁用"
    model = a.get("model") or "使用默认 Provider"
    skills = a.get("equipped_skills", [])
    skills_str = ", ".join(skills) if skills else "无"
    return (
        f"  • **{display_name}** (`{name}`) — {enabled}\n"
        f"    描述: {description}\n"
        f"    模型: {model}\n"
        f"    技能: {skills_str}"
    )


def _format_voice_provider(vp: dict) -> str:
    """格式化单个语音 Provider 为可读文本"""
    name = vp.get("name", "?")
    model = vp.get("model", "未配置") or "未配置"
    voice = vp.get("voice", "默认") or "默认"
    voice_type = vp.get("voice_type", "preset")
    enabled = "✅ 启用" if vp.get("enabled") else "❌ 禁用"
    key_status = "✅ 已配置" if vp.get("api_key_configured") else "⚠️ 未配置"
    type_label = "预设音色" if voice_type == "preset" else "声音复刻"
    return (
        f"  • **{name}** — {enabled}\n"
        f"    模型: {model} | 音色: {voice} ({type_label})\n"
        f"    API Key: {key_status}"
    )


def _format_skill(s: dict) -> str:
    """格式化单个技能为可读文本"""
    name = s.get("name", "?")
    display_name = s.get("display_name", name)
    description = s.get("description", "")
    enabled = "✅" if s.get("enabled") else "❌"
    func_count = len(s.get("functions", []))
    return f"  • {enabled} **{display_name}** (`{name}`) — {description} [{func_count} 个函数]"


# ============================================================
# 工具：系统状态
# ============================================================

async def system_status(client: ApiClient) -> str:
    """获取 AI 语音助手的系统概览状态，包括后端健康状态、Provider 数量、智能体数量和语音配置摘要"""
    try:
        health = await client.check_health()
        settings = await client.get_settings()
        providers = (await client.list_providers()).get("providers", [])
        agents = (await client.list_agents()).get("agents", [])
        voice_list = (await client.list_voice_providers()).get("providers", [])
    except RuntimeError as e:
        return f"❌ 无法连接后端服务: {e}"

    # 后端状态
    lines = [
        "## 🎙️ AI 语音助手 — 系统概览\n",
        f"**服务状态**: {health.get('status', 'unknown')}",
        f"**版本**: {health.get('version', 'unknown')}",
        f"**语音对话**: {'✅ 已开启' if settings.get('enable_voice_dialogue') else '❌ 已关闭'}",
        "",
        f"**LLM Provider 数量**: {len(providers)}",
        f"**智能体数量**: {len(agents)}",
        f"**语音 Provider 数量**: {len(voice_list)}",
        "",
    ]

    # 默认 Provider
    dp = settings.get("default_provider")
    if dp:
        lines.append(f"**默认 LLM Provider**: {dp.get('name', '?')} — {dp.get('model', '?')}")
        lines.append("")

    # 关键配置
    lines.extend([
        "### 关键配置",
        f"- **NLU Provider**: `{settings.get('nlu_provider_name', '未配置')}`",
        f"- **Dialog Provider**: `{settings.get('dialog_provider_name', '未配置')}`",
        f"- **语音 Provider**: `{settings.get('voice_provider', {}).get('name', '未配置')}`",
    ])

    return "\n".join(lines)


# ============================================================
# 工具：LLM Provider 管理
# ============================================================

async def list_providers(client: ApiClient) -> str:
    """列出所有已配置的 LLM Provider（大模型接口），包含每个 Provider 的模型名称、API 地址和 Key 配置状态"""
    data = await client.list_providers()
    providers = data.get("providers", [])
    if not providers:
        return "当前没有配置任何 LLM Provider。"

    lines = [f"## LLM Provider 列表（共 {len(providers)} 个）\n"]
    for p in providers:
        lines.append(_format_provider(p))
    return "\n".join(lines)


async def get_provider(client: ApiClient, name: str) -> str:
    """获取指定 LLM Provider 的详细配置（API 地址、模型、max_tokens、temperature 等）

    Args:
        name: Provider 名称（如 "default"、"deepseek"）
    """
    try:
        p = await client.get_provider(name)
    except RuntimeError as e:
        return f"❌ {e}"

    return (
        f"## LLM Provider: {p.get('name', name)}\n\n"
        f"- **API Base**: `{p.get('api_base', '未配置')}`\n"
        f"- **模型**: {p.get('model', '未配置')}\n"
        f"- **Max Tokens**: {p.get('max_tokens', 2048)}\n"
        f"- **Temperature**: {p.get('temperature', 0.7)}\n"
        f"- **API Key**: {'✅ 已配置' if p.get('api_key_configured') else '⚠️ 未配置'}"
    )


async def create_provider(
    client: ApiClient,
    name: str,
    api_base: str,
    api_key: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """创建一个新的 LLM Provider（大模型接口配置）

    Args:
        name: Provider 唯一标识名（如 "deepseek"、"ollama"）
        api_base: API 基础地址（如 "https://api.deepseek.com/v1"）
        api_key: API 密钥（可选，本地模型可留空）
        model: 模型名称（如 "deepseek-chat"）
        max_tokens: 最大生成 token 数（默认 2048）
        temperature: 生成温度（0~2，默认 0.7）
    """
    payload = {
        "name": name,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        result = await client.create_provider(payload)
        return (
            f"✅ **Provider '{name}' 创建成功**\n\n"
            f"- API Base: `{result.get('api_base', api_base)}`\n"
            f"- 模型: {result.get('model', model) or '未配置'}\n"
            f"- API Key: {'已配置' if result.get('api_key_configured') else '未配置'}"
        )
    except RuntimeError as e:
        return f"❌ 创建 Provider 失败: {e}"


async def update_provider(
    client: ApiClient,
    name: str,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """更新已有的 LLM Provider 配置（仅传入需要修改的字段）

    Args:
        name: Provider 名称（如 "default"）
        api_base: API 基础地址
        api_key: API 密钥
        model: 模型名称
        max_tokens: 最大生成 token 数
        temperature: 生成温度（0~2）
    """
    # 先获取当前配置，确保 Provider 存在
    try:
        current = await client.get_provider(name)
    except RuntimeError as e:
        return f"❌ {e}"

    payload: Dict[str, Any] = {
        "name": name,
        "api_base": api_base if api_base is not None else current.get("api_base", ""),
        "api_key": api_key if api_key is not None else "",
        "model": model if model is not None else current.get("model", ""),
        "max_tokens": max_tokens if max_tokens is not None else current.get("max_tokens", 2048),
        "temperature": temperature if temperature is not None else current.get("temperature", 0.7),
    }
    try:
        result = await client.update_provider(name, payload)
        return (
            f"✅ **Provider '{name}' 更新成功**\n\n"
            f"- API Base: `{result.get('api_base', payload['api_base'])}`\n"
            f"- 模型: {result.get('model', payload['model']) or '未配置'}\n"
            f"- API Key: {'已配置' if result.get('api_key_configured') else '未配置'}"
        )
    except RuntimeError as e:
        return f"❌ 更新 Provider 失败: {e}"


async def delete_provider(client: ApiClient, name: str) -> str:
    """删除指定的 LLM Provider（不允许删除默认 Provider "default"）

    Args:
        name: 要删除的 Provider 名称
    """
    try:
        result = await client.delete_provider(name)
        return f"✅ {result.get('message', f'Provider \"{name}\" 已删除')}"
    except RuntimeError as e:
        return f"❌ 删除 Provider 失败: {e}"


# ============================================================
# 工具：多智能体管理
# ============================================================

async def list_agents(client: ApiClient) -> str:
    """列出所有已注册的智能体，包括每个智能体的启用状态、模型配置、描述的完整摘要"""
    data = await client.list_agents()
    agents = data.get("agents", [])
    if not agents:
        return "当前没有注册任何智能体。"

    lines = [f"## 智能体列表（共 {len(agents)} 个）\n"]
    for a in agents:
        lines.append(_format_agent(a))
        lines.append("")
    return "\n".join(lines)


async def get_agent(client: ApiClient, name: str) -> str:
    """获取指定智能体的完整配置详情

    Args:
        name: 智能体名称（如 "general_chat"、"code_expert"）
    """
    try:
        a = await client.get_agent(name)
    except RuntimeError as e:
        return f"❌ {e}"

    lines = [
        f"## 智能体: {a.get('display_name', name)} (`{name}`)\n",
        f"**状态**: {'✅ 启用' if a.get('enabled') else '❌ 禁用'}",
        f"**描述**: {a.get('description', '无')}",
        f"**系统提示词**: {a.get('system_prompt', '无')[:500]}",
        "",
        "### 模型配置",
        f"- **模型**: {a.get('model') or '使用默认 Provider'}",
        f"- **API Base**: {a.get('api_base') or '使用默认 Provider'}",
        f"- **Temperature**: {a.get('temperature', 0.7)}",
        f"- **Max Tokens**: {a.get('max_tokens', 2048)}",
        "",
    ]

    skills = a.get("equipped_skills", [])
    if skills:
        lines.append(f"**装配技能**: {', '.join(skills)}")
    if a.get("personality"):
        lines.append(f"**性格**: {a['personality']}")

    return "\n".join(lines)


async def update_agent(
    client: ApiClient,
    name: str,
    enabled: Optional[bool] = None,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    personality: Optional[str] = None,
    system_prompt: Optional[str] = None,
    equipped_skills: Optional[List[str]] = None,
) -> str:
    """更新指定智能体的配置（仅传入需要修改的字段）

    Args:
        name: 智能体名称（如 "general_chat"）
        enabled: 是否启用
        model: 使用的模型名称（空字符串表示使用默认 Provider）
        api_base: API 地址（空字符串表示使用默认 Provider）
        temperature: 生成温度（0~2）
        max_tokens: 最大生成 token 数
        personality: 性格特质描述
        system_prompt: 系统提示词（自定义角色行为）
        equipped_skills: 装配的技能名称列表
    """
    # 构建仅含已设置字段的 payload
    payload: Dict[str, Any] = {}
    if enabled is not None:
        payload["enabled"] = enabled
        # 启用时确保 model 不为空
        if enabled:
            current = await client.get_agent(name)
            final_model = model or current.get("model", "")
            if not final_model:
                return f"❌ 无法启用 '{name}'：请先配置模型（model 不能为空）"
    if model is not None:
        payload["model"] = model
    if api_base is not None:
        payload["api_base"] = api_base
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if personality is not None:
        payload["personality"] = personality
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if equipped_skills is not None:
        payload["equipped_skills"] = equipped_skills

    if not payload:
        return "⚠️ 未提供有效的更新字段。"

    try:
        result = await client.update_agent(name, payload)
        return f"✅ **智能体 '{name}' 更新成功**\n\n更新内容: {_format_json(result.get('updates', payload))}"
    except RuntimeError as e:
        return f"❌ 更新智能体失败: {e}"


# ============================================================
# 工具：语音 Provider 管理
# ============================================================

async def list_voice_providers(client: ApiClient) -> str:
    """列出所有已配置的语音合成（TTS）Provider，包含模型、音色和启用状态"""
    data = await client.list_voice_providers()
    providers = data.get("providers", [])
    if not providers:
        return "当前没有配置任何语音 Provider。"

    lines = [f"## 语音 Provider 列表（共 {len(providers)} 个）\n"]
    for vp in providers:
        lines.append(_format_voice_provider(vp))
    return "\n".join(lines)


async def create_voice_provider(
    client: ApiClient,
    name: str,
    api_base: str,
    api_key: str = "",
    model: str = "glm-tts",
    voice: str = "female",
    voice_type: str = "preset",
    enabled: bool = False,
) -> str:
    """创建新的语音合成（TTS）Provider 配置

    Args:
        name: 语音 Provider 唯一标识名（如 "zhipu-glm"）
        api_base: API 基础地址
        api_key: API 密钥
        model: 语音模型（默认 "glm-tts"）
        voice: 音色 ID（预设音色时使用，如 "female"、"male"）
        voice_type: 音色类型 — "preset"（预设）或 "clone"（声音复刻）
        enabled: 是否立即启用
    """
    payload = {
        "name": name,
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "voice": voice,
        "voice_type": voice_type,
        "enabled": enabled,
    }
    try:
        result = await client.create_voice_provider(payload)
        return (
            f"✅ **语音 Provider '{name}' 创建成功**\n\n"
            f"- 模型: {result.get('model', model)}\n"
            f"- 音色: {result.get('voice', voice)} ({result.get('voice_type', voice_type)})\n"
            f"- 状态: {'已启用' if result.get('enabled') else '未启用'}"
        )
    except RuntimeError as e:
        return f"❌ 创建语音 Provider 失败: {e}"


async def update_voice_provider(
    client: ApiClient,
    name: str,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    voice_type: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> str:
    """更新已有的语音 Provider 配置

    Args:
        name: 语音 Provider 名称
        api_base: API 基础地址
        api_key: API 密钥
        model: 语音模型名称
        voice: 音色 ID
        voice_type: 音色类型（"preset" 或 "clone"）
        enabled: 是否启用
    """
    current = await client.get_voice_provider_info(name)

    payload: Dict[str, Any] = {
        "name": name,
        "api_base": api_base if api_base is not None else current.get("api_base", ""),
        "api_key": api_key if api_key is not None else "",
        "model": model if model is not None else current.get("model", "glm-tts"),
        "voice": voice if voice is not None else current.get("voice", "female"),
        "voice_type": voice_type if voice_type is not None else current.get("voice_type", "preset"),
        "enabled": enabled if enabled is not None else current.get("enabled", False),
    }
    try:
        result = await client.update_voice_provider(name, payload)
        return (
            f"✅ **语音 Provider '{name}' 更新成功**\n\n"
            f"- 模型: {result.get('model', payload['model'])}\n"
            f"- 音色: {result.get('voice', payload['voice'])} ({result.get('voice_type', payload['voice_type'])})\n"
            f"- 状态: {'已启用' if result.get('enabled') else '未启用'}"
        )
    except RuntimeError as e:
        return f"❌ 更新语音 Provider 失败: {e}"


# ============================================================
# 工具：技能管理
# ============================================================

async def list_skills(client: ApiClient) -> str:
    """列出所有已注册的技能（Skill），技能是智能体可以调用的功能模块"""
    data = await client.list_skills()
    skills = data.get("skills", [])
    if not skills:
        return "当前没有注册任何技能。"

    lines = [f"## 技能列表（共 {len(skills)} 个）\n"]
    for s in skills:
        lines.append(_format_skill(s))
    return "\n".join(lines)


# ============================================================
# 工具：设置管理
# ============================================================

async def get_settings(client: ApiClient) -> str:
    """获取运行时的完整配置状态，包括语音开关、NLU/Dialog Provider 绑定、默认 Provider 和语音 Provider 信息"""
    settings = await client.get_settings()

    lines = [
        "## 运行时配置\n",
        f"**语音对话**: {'✅ 已开启' if settings.get('enable_voice_dialogue') else '❌ 已关闭'}",
        f"**NLU Provider**: `{settings.get('nlu_provider_name', '未配置')}`",
        f"**Dialog Provider**: `{settings.get('dialog_provider_name', '未配置')}`",
        "",
    ]

    dp = settings.get("default_provider")
    if dp:
        lines.append(f"**默认 LLM Provider**: {dp.get('name', '?')} — {dp.get('model', '?')}")
        lines.append("")

    vp = settings.get("voice_provider")
    if vp:
        lines.append(f"**语音 Provider**: {vp.get('name', '?')} ({vp.get('model', '?')})")
        lines.append(f"**语音开关**: {'开启' if vp.get('enabled') else '关闭'}")

    return "\n".join(lines)


async def update_settings(
    client: ApiClient,
    enable_voice_dialogue: Optional[bool] = None,
    nlu_provider_name: Optional[str] = None,
    dialog_provider_name: Optional[str] = None,
) -> str:
    """更新运行时配置（功能开关和 Provider 绑定）

    Args:
        enable_voice_dialogue: 是否开启语音对话模式（true=开启，false=关闭）
        nlu_provider_name: NLU 语义识别使用的 Provider 名称
        dialog_provider_name: 对话管理使用的 Provider 名称
    """
    payload: Dict[str, Any] = {}
    if enable_voice_dialogue is not None:
        payload["enable_voice_dialogue"] = enable_voice_dialogue
    if nlu_provider_name is not None:
        payload["nlu_provider_name"] = nlu_provider_name
    if dialog_provider_name is not None:
        payload["dialog_provider_name"] = dialog_provider_name

    if not payload:
        return "⚠️ 未提供有效的更新字段。"

    try:
        result = await client.update_settings(payload)
        return f"✅ **配置更新成功**\n\n更新内容: {_format_json(payload)}\n\n当前配置:\n```json\n{_format_json(result)}\n```"
    except RuntimeError as e:
        return f"❌ 更新配置失败: {e}"
