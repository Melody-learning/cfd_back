"""健康检查路由"""
import time

from fastapi import APIRouter

from app.config import get_settings
from app.mt5.connector import get_mt5

router = APIRouter(tags=["系统"])

_start_time = time.time()


@router.get("/api/v1/health")
async def health_check():
    """服务健康检查"""
    settings = get_settings()
    mt5 = get_mt5()
    return {
        "status": "ok",
        "mt5_connected": mt5.is_connected,
        "mt5_server": f"{settings.MT5_SERVER_HOST}:{settings.MT5_SERVER_PORT}",
        "uptime": int(time.time() - _start_time),
        "version": settings.APP_VERSION,
    }
