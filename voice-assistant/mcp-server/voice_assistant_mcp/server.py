"""
Voice Assistant MCP Server

为 AI 语音助手系统提供 MCP 协议接口，暴露管理工具供 LLM 调用。

用法:
  # 开发模式
  mcp dev server.py

  # 生产运行
  python -m voice_assistant_mcp.server

  # 或直接
  uv run python -m voice_assistant_mcp.server
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from voice_assistant_mcp.api_client import ApiClient, DEFAULT_BASE_URL
from voice_assistant_mcp import __version__

# ============================================================
# 日志配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("voice-assistant-mcp")


# ============================================================
# 生命周期管理
# ============================================================

class ServerContext:
    """MCP 服务器上下文 — 在 lifespan 中初始化，工具函数通过 ctx 访问"""
    def __init__(self):
        self.client: ApiClient | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[ServerContext]:
    """服务器生命周期管理：启动时初始化 API 客户端，关闭时清理"""
    base_url = os.environ.get("VOICE_ASSISTANT_API_URL", DEFAULT_BASE_URL)
    logger.info(f"MCP 服务器启动中... 后端地址: {base_url}")
    ctx = ServerContext()
    ctx.client = ApiClient(base_url=base_url)

    # 启动时验证后端连通性
    try:
        health = await ctx.client.check_health()
        logger.info(f"后端连接成功: {health.get('status', 'ok')}")
    except Exception as e:
        logger.warning(f"后端连接失败（启动后仍可重试）: {e}")

    try:
        yield ctx
    finally:
        await ctx.client.close()
        logger.info("MCP 服务器已关闭")


# ============================================================
# MCP 服务器实例
# ============================================================

mcp = FastMCP(
    "AI 语音助手管理",
    lifespan=app_lifespan,
    dependencies=["httpx", "pydantic"],
)


# ============================================================
# 辅助函数：从上下文获取 API 客户端
# ============================================================

def _get_client(ctx) -> ApiClient:
    """从 FastMCP Context 获取 API 客户端实例"""
    return ctx.request_context.lifespan_context.client


# ============================================================
# 工具注册 — 系统状态
# ============================================================

@mcp.tool(
    description="获取 AI 语音助手的系统概览状态，包括后端健康、Provider 数量、智能体数量和语音配置摘要",
)
async def system_status(ctx) -> str:
    from voice_assistant_mcp.tools import system_status as _tool
    return await _tool(_get_client(ctx))


# ============================================================
# 工具注册 — LLM Provider 管理
# ============================================================

@mcp.tool(
    description="列出所有已配置的 LLM Provider（大模型接口），包含模型名称、API 地址和 Key 配置状态",
)
async def list_providers(ctx) -> str:
    from voice_assistant_mcp.tools import list_providers as _tool
    return await _tool(_get_client(ctx))


@mcp.tool(
    description="获取指定 LLM Provider 的详细配置信息（API 地址、模型、max_tokens、temperature 等）",
)
async def get_provider(ctx, name: str) -> str:
    """获取指定 LLM Provider 的详细配置

    Args:
        name: Provider 名称（如 "default"、"deepseek"、"ollama"）
    """
    from voice_assistant_mcp.tools import get_provider as _tool
    return await _tool(_get_client(ctx), name=name)


@mcp.tool(
    description="创建一个新的 LLM Provider（大模型接口配置），需要提供名称、API 地址、模型等",
)
async def create_provider(
    ctx,
    name: str,
    api_base: str,
    api_key: str = "",
    model: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """创建新的 LLM Provider

    Args:
        name: Provider 唯一标识名（如 "deepseek"、"ollama"）
        api_base: API 基础地址（如 "https://api.deepseek.com/v1"）
        api_key: API 密钥（可选，本地模型可留空）
        model: 模型名称（如 "deepseek-chat"、"gpt-4o"）
        max_tokens: 最大生成 token 数（默认 2048）
        temperature: 生成温度（0~2，默认 0.7）
    """
    from voice_assistant_mcp.tools import create_provider as _tool
    return await _tool(_get_client(ctx), name=name, api_base=api_base,
                       api_key=api_key, model=model,
                       max_tokens=max_tokens, temperature=temperature)


@mcp.tool(
    description="更新已有的 LLM Provider 配置（如修改 API 地址、模型、Key 等），仅传入需要修改的字段",
)
async def update_provider(
    ctx,
    name: str,
    api_base: str = None,
    api_key: str = None,
    model: str = None,
    max_tokens: int = None,
    temperature: float = None,
) -> str:
    """更新 LLM Provider

    Args:
        name: Provider 名称（如 "default"）
        api_base: API 基础地址（可选）
        api_key: API 密钥（可选）
        model: 模型名称（可选）
        max_tokens: 最大生成 token 数（可选）
        temperature: 生成温度 0~2（可选）
    """
    from voice_assistant_mcp.tools import update_provider as _tool
    return await _tool(_get_client(ctx), name=name, api_base=api_base,
                       api_key=api_key, model=model,
                       max_tokens=max_tokens, temperature=temperature)


@mcp.tool(
    description="删除指定的 LLM Provider（不允许删除名为 'default' 的默认 Provider）",
    annotations={"destructiveHint": True},
)
async def delete_provider(ctx, name: str) -> str:
    """删除 LLM Provider

    Args:
        name: 要删除的 Provider 名称
    """
    from voice_assistant_mcp.tools import delete_provider as _tool
    return await _tool(_get_client(ctx), name=name)


# ============================================================
# 工具注册 — 多智能体管理
# ============================================================

@mcp.tool(
    description="列出所有已注册的智能体，包含启用状态、模型配置、描述和装配的技能",
)
async def list_agents(ctx) -> str:
    from voice_assistant_mcp.tools import list_agents as _tool
    return await _tool(_get_client(ctx))


@mcp.tool(
    description="获取指定智能体的完整配置详情，包括系统提示词、模型参数、性格和技能",
)
async def get_agent(ctx, name: str) -> str:
    """获取智能体详情

    Args:
        name: 智能体名称（如 "general_chat"、"code_expert"、"creative"）
    """
    from voice_assistant_mcp.tools import get_agent as _tool
    return await _tool(_get_client(ctx), name=name)


@mcp.tool(
    description="更新指定智能体的配置（启用状态、模型、提示词、性格、技能等），仅传入需要修改的字段",
)
async def update_agent(
    ctx,
    name: str,
    enabled: bool = None,
    model: str = None,
    api_base: str = None,
    temperature: float = None,
    max_tokens: int = None,
    personality: str = None,
    system_prompt: str = None,
    equipped_skills: list = None,
) -> str:
    """更新智能体配置

    Args:
        name: 智能体名称（如 "general_chat"）
        enabled: 是否启用
        model: 模型名称（空字符串表示使用默认 Provider）
        api_base: API 地址（空字符串表示使用默认 Provider）
        temperature: 生成温度 0~2
        max_tokens: 最大生成 token 数
        personality: 性格特质描述
        system_prompt: 系统提示词
        equipped_skills: 装配的技能名称列表，如 ["calculator", "datetime", "tell_joke"]
    """
    from voice_assistant_mcp.tools import update_agent as _tool
    return await _tool(_get_client(ctx), name=name, enabled=enabled,
                       model=model, api_base=api_base,
                       temperature=temperature, max_tokens=max_tokens,
                       personality=personality, system_prompt=system_prompt,
                       equipped_skills=equipped_skills)


# ============================================================
# 工具注册 — 语音 Provider 管理
# ============================================================

@mcp.tool(
    description="列出所有已配置的语音合成（TTS）Provider，包含模型名称、音色和启用状态",
)
async def list_voice_providers(ctx) -> str:
    from voice_assistant_mcp.tools import list_voice_providers as _tool
    return await _tool(_get_client(ctx))


@mcp.tool(
    description="创建新的语音合成（TTS）Provider 配置，支持预设音色和声音复刻",
)
async def create_voice_provider(
    ctx,
    name: str,
    api_base: str,
    api_key: str = "",
    model: str = "glm-tts",
    voice: str = "female",
    voice_type: str = "preset",
    enabled: bool = False,
) -> str:
    """创建语音 Provider

    Args:
        name: 语音 Provider 唯一标识名（如 "zhipu-glm"）
        api_base: API 基础地址
        api_key: API 密钥
        model: 语音模型（默认 "glm-tts"）
        voice: 音色 ID（预设音色时使用，如 "female"、"male"）
        voice_type: 音色类型 — "preset"（预设）或 "clone"（声音复刻）
        enabled: 是否立即启用
    """
    from voice_assistant_mcp.tools import create_voice_provider as _tool
    return await _tool(_get_client(ctx), name=name, api_base=api_base,
                       api_key=api_key, model=model, voice=voice,
                       voice_type=voice_type, enabled=enabled)


@mcp.tool(
    description="更新已有的语音 Provider 配置（模型、音色、启用状态等）",
)
async def update_voice_provider(
    ctx,
    name: str,
    api_base: str = None,
    api_key: str = None,
    model: str = None,
    voice: str = None,
    voice_type: str = None,
    enabled: bool = None,
) -> str:
    """更新语音 Provider

    Args:
        name: 语音 Provider 名称
        api_base: API 基础地址（可选）
        api_key: API 密钥（可选）
        model: 语音模型名称（可选）
        voice: 音色 ID（可选）
        voice_type: 音色类型 "preset" 或 "clone"（可选）
        enabled: 是否启用（可选）
    """
    from voice_assistant_mcp.tools import update_voice_provider as _tool
    return await _tool(_get_client(ctx), name=name, api_base=api_base,
                       api_key=api_key, model=model, voice=voice,
                       voice_type=voice_type, enabled=enabled)


# ============================================================
# 工具注册 — 技能管理
# ============================================================

@mcp.tool(
    description="列出所有已注册的技能（Skill），技能是智能体可以调用的功能模块，如计算器、日期时间、讲笑话等",
)
async def list_skills(ctx) -> str:
    from voice_assistant_mcp.tools import list_skills as _tool
    return await _tool(_get_client(ctx))


# ============================================================
# 工具注册 — 设置管理
# ============================================================

@mcp.tool(
    description="获取当前运行时的所有配置状态，包括语音对话开关、NLU Provider 绑定、Dialog Provider 绑定、默认 LLM Provider 和语音 Provider 信息",
)
async def get_settings(ctx) -> str:
    from voice_assistant_mcp.tools import get_settings as _tool
    return await _tool(_get_client(ctx))


@mcp.tool(
    description="更新运行时配置，可以开启/关闭语音对话模式，或绑定 NLU/Dialog 使用指定的 Provider",
)
async def update_settings(
    ctx,
    enable_voice_dialogue: bool = None,
    nlu_provider_name: str = None,
    dialog_provider_name: str = None,
) -> str:
    """更新运行时配置

    Args:
        enable_voice_dialogue: 是否开启语音对话模式（true=开启，false=关闭）
        nlu_provider_name: NLU 语义识别使用的 Provider 名称（如 "default"）
        dialog_provider_name: 对话管理使用的 Provider 名称（如 "deepseek"）
    """
    from voice_assistant_mcp.tools import update_settings as _tool
    return await _tool(_get_client(ctx),
                       enable_voice_dialogue=enable_voice_dialogue,
                       nlu_provider_name=nlu_provider_name,
                       dialog_provider_name=dialog_provider_name)


# ============================================================
# 入口点
# ============================================================

def main():
    """启动 MCP 服务器"""
    logger.info(f"Voice Assistant MCP Server v{__version__}")
    logger.info(f"后端 API 地址: {os.environ.get('VOICE_ASSISTANT_API_URL', DEFAULT_BASE_URL)}")
    mcp.run()


if __name__ == "__main__":
    main()
