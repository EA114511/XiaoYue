"""
HTTP API 客户端 — 封装与后端 REST API 的通信

提供统一的错误处理、超时管理、JSON 序列化，
所有 MCP 工具函数通过此客户端与后端交互。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("voice-assistant-mcp.api_client")

# 默认后端地址（可通过环境变量覆盖）
DEFAULT_BASE_URL = "http://localhost:8000"


class ApiClient:
    """
    轻量级 HTTP 客户端，封装后端的 REST API

    用法:
        client = ApiClient(base_url="http://localhost:8000")
        providers = await client.list_providers()
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json"},
        )

    async def close(self):
        """关闭底层 HTTP 连接"""
        await self._client.aclose()

    # ---------------------------------------------------------------
    # 底层请求方法
    # ---------------------------------------------------------------

    async def _get(self, path: str, **kwargs) -> Dict[str, Any]:
        """GET 请求"""
        resp = await self._client.get(path, **kwargs)
        return await self._handle_response(resp)

    async def _post(self, path: str, json: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """POST 请求"""
        resp = await self._client.post(path, json=json, **kwargs)
        return await self._handle_response(resp)

    async def _patch(self, path: str, json: Optional[Dict] = None, **kwargs) -> Dict[str, Any]:
        """PATCH 请求"""
        resp = await self._client.patch(path, json=json, **kwargs)
        return await self._handle_response(resp)

    async def _delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """DELETE 请求"""
        resp = await self._client.delete(path, **kwargs)
        return await self._handle_response(resp)

    @staticmethod
    async def _handle_response(resp: httpx.Response) -> Dict[str, Any]:
        """统一处理 HTTP 响应，提取 JSON 或构造错误信息"""
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.is_success:
            return data

        # 构造有意义的错误信息
        detail = data.get("detail", data.get("message", ""))
        if not detail:
            detail = f"HTTP {resp.status_code}: {resp.reason_phrase}"

        raise RuntimeError(f"API 请求失败 [{resp.status_code}]: {detail}")

    # ---------------------------------------------------------------
    # 健康检查
    # ---------------------------------------------------------------

    async def check_health(self) -> Dict[str, Any]:
        """检查后端服务状态"""
        data = await self._get("/api/v1/health")
        return {
            "status": data.get("status", "unknown"),
            "service": data.get("service", "voice-assistant"),
            "version": data.get("version", "unknown"),
        }

    # ---------------------------------------------------------------
    # Settings
    # ---------------------------------------------------------------

    async def get_settings(self) -> Dict[str, Any]:
        """获取完整运行时配置"""
        return await self._get("/api/v1/settings")

    async def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新运行时配置（enable_voice_dialogue / nlu_provider_name / dialog_provider_name）"""
        return await self._post("/api/v1/settings", json=updates)

    # ---------------------------------------------------------------
    # LLM Providers
    # ---------------------------------------------------------------

    async def list_providers(self) -> Dict[str, Any]:
        """获取所有 LLM Provider"""
        return await self._get("/api/v1/providers")

    async def get_provider(self, name: str) -> Dict[str, Any]:
        """获取单个 LLM Provider 详情"""
        return await self._get(f"/api/v1/providers/{name}")

    async def create_provider(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的 LLM Provider"""
        return await self._post("/api/v1/providers", json=data)

    async def update_provider(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新 LLM Provider"""
        return await self._patch(f"/api/v1/providers/{name}", json=data)

    async def delete_provider(self, name: str) -> Dict[str, Any]:
        """删除 LLM Provider"""
        return await self._delete(f"/api/v1/providers/{name}")

    # ---------------------------------------------------------------
    # Agents
    # ---------------------------------------------------------------

    async def list_agents(self) -> Dict[str, Any]:
        """获取所有智能体"""
        return await self._get("/api/v1/agents")

    async def get_agent(self, name: str) -> Dict[str, Any]:
        """获取单个智能体（通过 agents list 过滤）"""
        data = await self.list_agents()
        agents = data.get("agents", [])
        for agent in agents:
            if agent.get("name") == name:
                return agent
        raise RuntimeError(f"智能体 '{name}' 不存在")

    async def update_agent(self, name: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新智能体配置"""
        return await self._patch(f"/api/v1/agents/{name}", json=updates)

    # ---------------------------------------------------------------
    # Voice Providers
    # ---------------------------------------------------------------

    async def list_voice_providers(self) -> Dict[str, Any]:
        """获取所有语音 Provider"""
        return await self._get("/api/v1/voice-providers")

    async def create_voice_provider(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建语音 Provider"""
        return await self._post("/api/v1/voice-providers", json=data)

    async def get_voice_provider_info(self, name: str) -> Dict[str, Any]:
        """获取单个语音 Provider（通过列表过滤）"""
        data = await self.list_voice_providers()
        providers = data.get("providers", [])
        for vp in providers:
            if vp.get("name") == name:
                return vp
        raise RuntimeError(f"语音 Provider '{name}' 不存在")

    async def update_voice_provider(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新语音 Provider"""
        return await self._patch(f"/api/v1/voice-providers/{name}", json=data)

    # ---------------------------------------------------------------
    # Skills
    # ---------------------------------------------------------------

    async def list_skills(self) -> Dict[str, Any]:
        """获取所有技能"""
        return await self._get("/api/v1/skills")
