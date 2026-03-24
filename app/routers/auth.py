"""Authentication routes: register, login, refresh, logout."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    ErrorResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.services import auth_service
from app.services.jwt_service import (
    create_access_token,
    decode_token,
    get_current_user,
    hash_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@router.post("/register", response_model=RegisterResponse, responses={409: {"model": ErrorResponse}})
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new MT5 demo account and local mapping."""
    return await auth_service.register_user(
        email=req.email,
        password=req.password,
        nickname=req.nickname,
        db=db,
    )


@router.post("/login", response_model=LoginResponse, responses={401: {"model": ErrorResponse}})
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login via local mapping + MT5 password verification."""
    return await auth_service.login_user(
        email=req.email,
        password=req.password,
        db=db,
    )


@router.post("/refresh", response_model=RefreshResponse, responses={401: {"model": ErrorResponse}})
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh access token."""
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_INVALID", "message": "需要 refresh_token"}},
        )

    token_hash = hash_token(req.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    rt = result.scalar_one_or_none()
    if rt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_EXPIRED", "message": "Refresh token 已失效"}},
        )

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    access_token, expires_in = create_access_token(user.mt5_login)
    return {"access_token": access_token, "token_type": "bearer", "expires_in": expires_in}


@router.post("/logout", status_code=204)
async def logout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all refresh tokens for the current user."""
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.commit()
