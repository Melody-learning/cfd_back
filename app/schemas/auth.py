"""Pydantic schemas for authentication requests and responses."""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=16, description="至少 8 位，包含大小写、数字和特殊字符")
    nickname: str = Field(min_length=1, max_length=128, default="Trader")


class RegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    mt5_login: int
    expires_in: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    mt5_login: int
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ErrorResponse(BaseModel):
    error: dict = Field(
        ...,
        examples=[
            {
                "code": "AUTH_INVALID_PASSWORD",
                "message": "邮箱或密码错误",
            }
        ],
    )
