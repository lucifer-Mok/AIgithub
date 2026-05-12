"""
FastAPI 应用入口
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from scheduler import start_scheduler, stop_scheduler, get_scheduler_status
from api.routes import router
from api.config_routes import router as config_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    logger.info("Starting AI GitHub Tracker...")
    if settings.github_token:
        logger.info("GitHub Token: configured ✓")
    else:
        logger.warning("GitHub Token: not configured (rate limit: 60 req/hour)")
    start_scheduler()
    yield
    # 关闭时
    stop_scheduler()
    logger.info("Server shutdown complete")


app = FastAPI(
    title="AI GitHub Tracker",
    description="每日追踪 GitHub 上最热门的 AI 相关项目",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS，允许 Vue 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api")
app.include_router(config_router, prefix="/api")


@app.get("/")
def root():
    return {
        "name": "AI GitHub Tracker",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "github_token": bool(settings.github_token),
        "scheduler": get_scheduler_status(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
