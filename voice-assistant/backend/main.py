"""
AI语音助手 - 后端服务入口
作为 uvicorn 启动入口，通过 from app.main import app 导入应用实例
"""

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
