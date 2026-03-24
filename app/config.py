"""AstralW Gateway 配置模块"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用全局配置，从 .env 文件自动读取"""

    # --- MT5 服务器 ---
    MT5_SERVER_HOST: str = "43.128.39.163"
    MT5_SERVER_PORT: int = 443
    MT5_MANAGER_LOGIN: int = 1015
    MT5_MANAGER_PASSWORD: str = ""
    MT5_WEBAPI_PASSWORD: str = ""
    MT5_DEMO_GROUP: str = "demo\\retail"
    MT5_INITIAL_BALANCE: float = 10000.0
    MT5_USE_SSL_VERIFY: bool = False

    # --- JWT ---
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- 数据库 ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./astralw_gateway.db"

    # --- 应用 ---
    APP_NAME: str = "AstralW Gateway"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    """获取全局配置（缓存单例）"""
    return Settings()
