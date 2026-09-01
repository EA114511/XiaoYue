"""
AI语音助手 - FastAPI 应用工厂
创建 FastAPI 应用实例，配置中间件、路由、生命周期事件和异常处理
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import health, voice, conversation, functions, settings_router, providers_router, agents_router, voice_providers_router, skills_router
from app.api.websocket import voice_websocket_endpoint, voice_handler, session_manager
from app.core.config import settings
from app.core.database import DatabaseService, database_service
from app.core.dialog import DialogManager
from app.core.asr import ASRService
from app.core.ai_voice import AIVoiceService
from app.core.http_client import close_http_client
from app.skills.builtin import register_builtin_skills


# ============================================================
# 日志配置（控制台 + 文件）
# ============================================================
_log_handlers = [logging.StreamHandler()]
# 如果配置了日志文件路径，添加文件处理器
if settings.LOG_FILE:
    try:
        os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
        _log_handlers.append(
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        )
    except OSError:
        pass

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
)
logger = logging.getLogger("voice-assistant")


# ============================================================
# 全局服务实例（在 lifespan 中初始化和清理）
# ============================================================
class ApplicationServices:
    """应用级服务容器"""

    def __init__(self):
        self.database = database_service
        self.dialog_manager = DialogManager(db_service=self.database)
        self.asr_service = ASRService()
        self.ai_voice_service = AIVoiceService()

    async def initialize(self):
        """初始化所有服务并注入到 WebSocket handler 和 app.state"""
        logger.info("正在初始化数据库...")
        await self.database.initialize()
        logger.info("数据库初始化完成")

        logger.info("正在初始化语音识别服务...")
        await self.asr_service.initialize()
        # 设置 VAD 静音超时 500ms（WebSocket 流式识别语音结束判定）
        self.asr_service.silence_timeout = 0.5
        logger.info("语音识别服务初始化完成")

        logger.info("正在初始化 AI 语音大模型服务（TTS）...")
        await self.ai_voice_service.initialize()
        logger.info("AI 语音大模型服务初始化完成")

        # 注册内置技能
        logger.info("正在注册内置技能...")
        register_builtin_skills()
        logger.info("内置技能注册完成")

        # 将真实服务注入到 WebSocket handler 中
        voice_handler.asr_service = self.asr_service
        voice_handler.dialog_manager = self.dialog_manager
        voice_handler.ai_voice_service = self.ai_voice_service

        logger.info("所有服务初始化完成")

    async def shutdown(self):
        """清理所有服务资源"""
        logger.info("正在清理服务资源...")
        await self.asr_service.cleanup()
        await self.ai_voice_service.cleanup()
        await close_http_client()
        await self.database.cleanup()
        logger.info("服务资源清理完成")

    def inject_to_app(self, app: FastAPI):
        """将服务注入到 FastAPI app.state，供 REST 端点使用"""
        app.state.asr_service = self.asr_service
        app.state.ai_voice_service = self.ai_voice_service
        app.state.dialog_manager = self.dialog_manager
        app.state.database = self.database


# 全局服务实例
services = ApplicationServices()


# ============================================================
# 后台任务：定时清理过期会话
# ============================================================
_cleanup_task = None


async def _periodic_cleanup(interval: int = 300):
    """每 interval 秒清理一次过期会话"""
    while True:
        await asyncio.sleep(interval)
        try:
            cleaned = services.dialog_manager.cleanup_expired()
            if cleaned > 0:
                logger.info(f"[后台任务] 清理了 {cleaned} 个过期会话")
        except Exception as e:
            logger.error(f"[后台任务] 清理过期会话时出错: {e}")


# ============================================================
# 应用生命周期管理
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    应用生命周期管理器
    - startup: 服务启动时初始化资源
    - shutdown: 服务关闭时清理资源
    """
    # --- startup ---
    logger.info("=" * 50)
    logger.info("AI语音助手服务正在启动...")
    logger.info(f"API文档地址: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info("=" * 50)

    await services.initialize()
    # 将服务注入到 app.state，供 REST 端点使用
    services.inject_to_app(app)

    # 启动后台清理任务
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_periodic_cleanup())
    logger.info("[后台任务] 会话清理任务已启动（间隔 5 分钟）")

    yield

    # --- shutdown ---
    logger.info("=" * 50)
    logger.info("AI语音助手服务正在关闭...")
    logger.info("=" * 50)

    # 取消后台任务
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    await services.shutdown()


# ============================================================
# FastAPI 应用实例
# ============================================================
app = FastAPI(
    title="AI语音助手 API",
    description="基于 FastAPI 的智能语音助手后端服务\n\n"
    "## 功能特性\n"
    "- 实时语音识别 (ASR) via Whisper\n"
    "- AI 大模型语音合成 (TTS)\n"
    "- 自然语言理解 (NLU) 与意图识别\n"
    "- 多智能体协同对话管理\n"
    "- 功能调用（天气查询、设备控制等）",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ============================================================
# CORS 中间件 - 允许前端跨域访问
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# API Token 鉴权中间件
# 保护所有写操作（POST/PUT/PATCH/DELETE），防止未授权修改配置
# 说明：仅当 settings.API_TOKEN 非空时启用；读操作与 CORS 预检放行
# ============================================================
@app.middleware("http")
async def api_token_guard(request: Request, call_next):
    """校验写操作请求头中的 API Token，不匹配则返回 401"""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = settings.API_TOKEN
        if token:
            provided = request.headers.get("X-API-Token", "")
            if not provided:
                auth = request.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    provided = auth[7:].strip()
            if provided != token:
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "未授权",
                        "message": "缺少或错误的 API Token",
                        "type": "unauthorized",
                    },
                )
    return await call_next(request)


# ============================================================
# 全局异常处理
# ============================================================
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """参数校验异常处理"""
    logger.warning(f"参数错误: {exc}")
    return JSONResponse(
        status_code=400,
        content={
            "error": "参数错误",
            "message": str(exc),
            "type": "value_error",
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底异常处理"""
    logger.error(f"未捕获异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "服务器内部错误",
            "message": "服务暂时不可用，请稍后重试",
            "type": "internal_error",
        },
    )


# ============================================================
# REST API 路由注册
# ============================================================
# 健康检查路由
app.include_router(health, prefix="/api/v1/health", tags=["健康检查"])

# 语音处理路由
app.include_router(voice, prefix="/api/v1/voice", tags=["语音处理"])

# 对话管理路由
app.include_router(conversation, prefix="/api/v1/conversation", tags=["对话管理"])

# 功能调用路由
app.include_router(functions, prefix="/api/v1/functions", tags=["功能调用"])

# 配置管理路由
app.include_router(settings_router, prefix="/api/v1/settings", tags=["配置管理"])

# 多智能体管理路由
app.include_router(agents_router, prefix="/api/v1/agents", tags=["多智能体管理"])

# Provider 管理路由
app.include_router(providers_router, prefix="/api/v1/providers", tags=["Provider 管理"])

# 语音 Provider 管理路由
app.include_router(voice_providers_router, prefix="/api/v1/voice-providers", tags=["语音 Provider 管理"])

# 技能管理路由
app.include_router(skills_router, prefix="/api/v1/skills", tags=["技能管理"])


# ============================================================
# WebSocket 路由 - 实时语音对话
# 实现在 app/api/websocket.py 中
# ============================================================
@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket):
    """WebSocket 语音对话端点，委托给 websocket 模块处理"""
    await voice_websocket_endpoint(websocket)


# ============================================================
# 静态文件服务（可选）
# ============================================================
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============================================================
# 根路径
# ============================================================
@app.get("/")
async def root():
    """服务根路径"""
    return {
        "service": "AI语音助手",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


# ============================================================
# 健康检查接口
# ============================================================
@app.get("/health")
async def health_check():
    """
    健康检查端点
    用于 Docker 容器编排和负载均衡器的健康检测
    """
    return {
        "status": "healthy",
        "service": "voice-assistant",
        "version": "1.0.0",
        "ws_connections": session_manager.active_count,
    }
