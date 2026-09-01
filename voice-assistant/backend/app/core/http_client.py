"""
统一 HTTP 客户端管理模块

提供一个进程内共享的 httpx.AsyncClient，复用底层连接池，
避免在 nlu / dialog / multi_agent / weather 等模块中反复创建、
销毁临时客户端带来的连接开销。

使用方式:
    from app.core.http_client import get_http_client, close_http_client

    client = get_http_client()
    resp = await client.post(url, json=..., timeout=httpx.Timeout(15.0))

注意:
  - 共享客户端采用惰性创建，首次调用必须在运行中的事件循环内。
  - 应用关闭时应调用 close_http_client() 释放连接池。
"""

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("voice-assistant.http_client")

# 进程内共享客户端（惰性创建，避免在事件循环启动前创建）
_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """获取共享的 httpx.AsyncClient（惰性创建并复用连接池）"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            # 默认超时取较宽松值，各调用点可通过 timeout 参数单独覆盖
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=getattr(settings, "LLM_MAX_CONNECTIONS", 5),
                max_keepalive_connections=5,
            ),
        )
        logger.info("[HTTP] 共享 httpx 客户端已创建")
    return _client


async def close_http_client() -> None:
    """关闭共享客户端并释放连接池（应用 shutdown 时调用）"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        logger.info("[HTTP] 共享 httpx 客户端已关闭")
    _client = None
