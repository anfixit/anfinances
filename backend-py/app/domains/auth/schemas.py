"""Pydantic-схемы домена auth."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = [
    "LoginRequest",
    "RefreshRequest",
    "RegisterRequest",
    "TokenPair",
    "UserRead",
]


class RegisterRequest(BaseModel):
    """Данные регистрации. Пароль проверяется политикой в сервисе."""

    email: EmailStr
    password: str
    name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    """Пара токенов. token_type фиксирован для совместимости с OAuth2."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str | None
    timezone: str
    default_currency: str
    locale: str
    is_active: bool
    is_verified: bool
    created_at: datetime
