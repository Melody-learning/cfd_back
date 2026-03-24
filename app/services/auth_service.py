"""Authentication business logic."""
import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import RefreshToken, User
from app.mt5.connector import MT5APIError, MT5ConnectionError, get_mt5
from app.services.jwt_service import (
    create_access_token,
    create_refresh_token_str,
    hash_token,
)

logger = logging.getLogger(__name__)


async def register_user(
    email: str, password: str, nickname: str, db: AsyncSession
) -> dict:
    """
    Register a new platform user:
    1. Check email uniqueness
    2. Call MT5 user/add to create a demo account
    3. Call MT5 trade/balance to credit initial funds
    4. Save local email -> mt5_login mapping
    5. Issue JWT tokens
    """
    settings = get_settings()
    mt5 = get_mt5()

    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "EMAIL_EXISTS", "message": "该邮箱已注册"}},
        )

    try:
        user_add_data = await mt5.get(
            "/api/user/add",
            params={
                "group": settings.MT5_DEMO_GROUP,
                "name": nickname,
                "leverage": "100",
                "pass_main": password,
                "pass_investor": password,
            },
        )
    except MT5APIError as e:
        logger.error("MT5 user/add failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "MT5_USER_ADD_FAILED", "message": f"创建 MT5 账户失败: {e.retcode}"}},
        )
    except MT5ConnectionError as e:
        logger.error("MT5 connection failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}},
        )

    mt5_login = int(user_add_data.get("login", user_add_data.get("answer", {}).get("Login", 0)))
    if mt5_login == 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "MT5_USER_ADD_FAILED", "message": "未能获取 MT5 login"}},
        )

    logger.info("MT5 demo account created: login=%s", mt5_login)

    try:
        await mt5.get(
            "/api/trade/balance",
            params={
                "login": str(mt5_login),
                "type": "2",
                "balance": str(settings.MT5_INITIAL_BALANCE),
                "comment": "initial_deposit",
            },
        )
        logger.info("Initial balance credited: %s", settings.MT5_INITIAL_BALANCE)
    except Exception as e:
        logger.warning("Initial balance credit failed after account creation: %s", e)

    user = User(email=email, mt5_login=mt5_login, nickname=nickname)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token, expires_in = create_access_token(mt5_login)
    refresh_token, refresh_expires = create_refresh_token_str(user.id)

    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_expires,
    )
    db.add(rt)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mt5_login": mt5_login,
        "expires_in": expires_in,
    }


async def login_user(email: str, password: str, db: AsyncSession) -> dict:
    """
    Login flow:
    1. Look up local email -> mt5_login mapping
    2. Verify password with MT5
    3. Issue JWT tokens
    """
    mt5 = get_mt5()

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_FAILED", "message": "邮箱或密码错误"}},
        )

    try:
        await mt5.get(
            "/api/user/check_password",
            params={
                "login": str(user.mt5_login),
                "type": "main",
                "password": password,
            },
        )
    except MT5APIError as e:
        logger.info("MT5 password verification failed (login=%s): %s", user.mt5_login, e.retcode)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_INVALID_PASSWORD",
                    "message": "邮箱或密码错误",
                    "mt5_retcode": e.retcode,
                }
            },
        )
    except MT5ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "MT5_UNAVAILABLE", "message": "MT5 服务不可用"}},
        )

    access_token, expires_in = create_access_token(user.mt5_login)
    refresh_token, refresh_expires = create_refresh_token_str(user.id)

    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_expires,
    )
    db.add(rt)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "mt5_login": user.mt5_login,
        "expires_in": expires_in,
    }
