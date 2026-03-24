"""AstralW Gateway — FastAPI 入口"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db
from app.mt5.connector import MT5APIError, MT5ConnectionError, get_mt5
from app.routers import account, auth, chart, health, market, trade

# 日志配置
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库和 MT5 连接，关闭时断开"""
    settings = get_settings()
    logger.info("🚀 %s v%s 启动中...", settings.APP_NAME, settings.APP_VERSION)

    # 初始化数据库
    await init_db()
    logger.info("📦 数据库已初始化")

    # 连接 MT5（带重试）
    mt5 = get_mt5()
    for attempt in range(3):
        try:
            await mt5.connect()
            break
        except Exception as e:
            if attempt < 2:
                logger.warning("MT5 连接失败（第 %d 次），%ds 后重试: %s", attempt + 1, 2 ** attempt, e)
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("⚠️ MT5 连接失败（3 次重试后），服务仍可启动但交易功能不可用: %s", e)

    yield

    # 关闭
    await mt5.disconnect()
    logger.info("👋 服务已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AstralW CFD 交易中间件 — MT5 Web API Gateway",
        lifespan=lifespan,
    )

    # CORS（允许 Android 客户端访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(market.router)
    app.include_router(chart.router)
    app.include_router(trade.router)
    app.include_router(account.router)

    # 全局异常处理：MT5 连接/API 错误统一转为友好响应
    @app.exception_handler(MT5ConnectionError)
    async def mt5_connection_error_handler(request: Request, exc: MT5ConnectionError):
        return JSONResponse(
            status_code=503,
            content={"detail": {"error": {"code": "MT5_UNAVAILABLE", "message": str(exc)}}},
        )

    @app.exception_handler(MT5APIError)
    async def mt5_api_error_handler(request: Request, exc: MT5APIError):
        return JSONResponse(
            status_code=502,
            content={"detail": {"error": {"code": "MT5_API_ERROR", "message": str(exc), "retcode": exc.retcode}}},
        )

    return app


app = create_app()
