"""
MCP Bridge 适配器

将 MCP (Model Context Protocol) 服务器的工具注册为系统 Skill，
使智能体可以通过统一 SkillRegistry 调用 MCP 工具。

使用方式：
  1. 在配置中心添加 MCP 服务器连接信息 (url, api_key 等)
  2. 调用 discover_mcp_tools() 拉取工具列表
  3. 工具自动注册为 Skill，可装配给智能体
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from app.skills import SkillDefinition as Skill, SkillFunction, skill_registry

logger = logging.getLogger(__name__)

# ============================================================
# 持久化路径
# ============================================================

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
MCP_SERVERS_FILE = os.path.join(DATA_DIR, "mcp_servers.json")


# ============================================================
# MCP 服务器连接配置
# ============================================================

@dataclass
class MCPServerConfig:
    """MCP 服务器连接配置"""
    name: str                              # 唯一标识名
    display_name: str = ""                 # 显示名称
    url: str = ""                          # MCP 服务器地址 (SSE endpoint)
    api_key: str = ""                      # 可选 API Key
    enabled: bool = True                   # 是否启用
    tools: list[dict] = field(default_factory=list)  # 缓存的工具列表
    _headers: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
        if self.api_key:
            self._headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }


# ============================================================
# MCP 注册表 — 管理所有 MCP 服务器连接
# ============================================================

class MCPRegistry:
    """
    管理 MCP 服务器连接和工具发现。
    每个 MCP 服务器的工具会被注册为一个 Skill（skill name = mcp_{server_name}）。
    """

    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}

    # --------------------------------------------------
    # 持久化
    # --------------------------------------------------

    def _save(self) -> None:
        """将 MCP 服务器配置持久化到 JSON 文件"""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = []
            for s in self._servers.values():
                data.append({
                    "name": s.name,
                    "display_name": s.display_name,
                    "url": s.url,
                    "enabled": s.enabled,
                    "tools": s.tools,
                })
            with open(MCP_SERVERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[MCP] 配置已持久化: {len(data)} 个服务器")
        except Exception as e:
            logger.warning(f"[MCP] 持久化失败: {e}")

    def load_servers(self) -> None:
        """从 JSON 文件加载 MCP 服务器配置"""
        if not os.path.exists(MCP_SERVERS_FILE):
            logger.debug("[MCP] 无持久化配置，跳过加载")
            return
        try:
            with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                config = MCPServerConfig(
                    name=item["name"],
                    display_name=item.get("display_name", item["name"]),
                    url=item.get("url", ""),
                    enabled=item.get("enabled", True),
                    tools=item.get("tools", []),
                )
                self._servers[config.name] = config
                # 若已有缓存的工具，直接注册为 Skill
                if config.enabled and config.tools:
                    self._register_skill(config.name, config.tools)
            logger.info(f"[MCP] 已加载 {len(data)} 个服务器配置")
        except Exception as e:
            logger.warning(f"[MCP] 加载配置失败: {e}")

    def register_server(self, config: MCPServerConfig) -> None:
        """注册一个 MCP 服务器"""
        self._servers[config.name] = config
        self._save()  # 自动持久化
        logger.info(f"[MCP] 已注册服务器: {config.name} ({config.url})")

    def remove_server(self, name: str) -> None:
        """移除 MCP 服务器及其注册的技能"""
        self._unregister_skill(name)
        self._servers.pop(name, None)
        self._save()  # 自动持久化
        logger.info(f"[MCP] 已移除服务器: {name}")

    def get_server(self, name: str) -> MCPServerConfig | None:
        return self._servers.get(name)

    def list_servers(self) -> list[MCPServerConfig]:
        return list(self._servers.values())

    async def discover_tools(self, server_name: str) -> list[dict]:
        """
        从 MCP 服务器发现工具列表。
        发送 POST /tools/list 请求，返回工具定义列表。
        """
        server = self._servers.get(server_name)
        if not server:
            raise ValueError(f"未知 MCP 服务器: {server_name}")

        try:
            import aiohttp
            async with aiohttp.ClientSession(headers=server._headers) as session:
                async with session.post(
                    f"{server.url.rstrip('/')}/tools/list",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"MCP 服务器返回 {resp.status}: {text}")
                    data = await resp.json()
                    tools = data.get("result", {}).get("tools", [])
                    server.tools = tools
                    self._register_skill(server_name, tools)
                    return tools
        except ImportError:
            raise RuntimeError("需要安装 aiohttp: pip install aiohttp")
        except Exception as e:
            logger.error(f"[MCP] 发现工具失败 {server_name}: {e}")
            raise

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """调用 MCP 服务器上的工具"""
        server = self._servers.get(server_name)
        if not server:
            raise ValueError(f"未知 MCP 服务器: {server_name}")

        try:
            import aiohttp
            async with aiohttp.ClientSession(headers=server._headers) as session:
                async with session.post(
                    f"{server.url.rstrip('/')}/tools/call",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": arguments},
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"MCP 工具调用失败 {tool_name}: {resp.status} {text}")
                    data = await resp.json()
                    return data.get("result", {})
        except ImportError:
            raise RuntimeError("需要安装 aiohttp: pip install aiohttp")

    # --------------------------------------------------
    # 内部：将 MCP 工具注册/注销为 Skill
    # --------------------------------------------------

    def _register_skill(self, server_name: str, tools: list[dict]) -> None:
        """将 MCP 工具列表注册为一个 Skill"""
        skill_name = f"mcp_{server_name}"
        server = self._servers.get(server_name)
        display_name = server.display_name if server else server_name

        functions: list[SkillFunction] = []
        for tool in tools:
            fn_name = tool.get("name", "unknown")
            fn_desc = tool.get("description", "")
            fn_params = tool.get("inputSchema", tool.get("parameters", {}))
            handler = self._make_handler(server_name, fn_name)
            functions.append(SkillFunction(
                name=fn_name,
                description=fn_desc,
                handler=handler,
                parameters=fn_params,
            ))

        skill = Skill(
            name=skill_name,
            display_name=f"MCP: {display_name}",
            description=f"通过 MCP 协议连接的服务器 {display_name} 提供的工具",
            functions=functions,
        )
        skill_registry.register(skill)
        logger.info(f"[MCP] 已注册技能 {skill_name}，包含 {len(functions)} 个工具")

    def _unregister_skill(self, server_name: str) -> None:
        """注销 MCP 服务器对应的 Skill"""
        skill_name = f"mcp_{server_name}"
        skill_registry.unregister(skill_name)
        logger.info(f"[MCP] 已注销技能 {skill_name}")

    def _make_handler(self, server_name: str, tool_name: str) -> Callable:
        """创建 MCP 工具调用的处理函数"""
        async def handler(**kwargs) -> str:
            result = await self.call_tool(server_name, tool_name, kwargs)
            return json.dumps(result, ensure_ascii=False, default=str)
        handler.__name__ = tool_name
        handler.__qualname__ = f"MCPHandler.{server_name}.{tool_name}"
        return handler


# ============================================================
# 全局单例
# ============================================================

mcp_registry = MCPRegistry()
