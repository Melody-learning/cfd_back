"""JWT 签发与验证服务"""
import hashlib
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import RefreshToken, User

security = HTTPBearer()


def create_access_token(mt5_login: int) -> tuple[str, int]:
    """
    签发 access_token。

    Returns:
        (token_str, expires_in_seconds)
    """
    settings = get_settings()
    expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": str(mt5_login),
        "exp": expire,
        "type": "access",
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire_minutes * 60


def create_refresh_token_str(user_id: int) -> tuple[str, datetime]:
    """
    签发 refresh_token 字符串。

    Returns:
        (token_str, expires_at)
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expire


def hash_token(token: str) -> str:
    """对 refresh token 做 SHA-256 哈希存储"""
    return hashlib.sha256(token.encode()).hexdigest()


def decode_token(token: str) -> dict:
    """解码 JWT，失败抛出 HTTPException 401"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_INVALID", "message": "Token 无效或已过期"}},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI 依赖注入：从 Bearer Token 中获取当前用户。

    解析 access_token 中的 mt5_login，查询本地数据库返回 User 对象。
    """
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_INVALID", "message": "需要 access_token"}},
        )

    mt5_login = int(payload["sub"])
    result = await db.execute(select(User).where(User.mt5_login == mt5_login))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}},
        )
    return user
