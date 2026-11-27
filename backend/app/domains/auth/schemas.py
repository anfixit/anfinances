"""Pydantic-схемы домена auth."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = [
    "AccessToken",
    "ChangePasswordRequest",
    "LoginRequest",
    "RegisterRequest",
    "TokenPair",
    "UserRead",
]


class RegisterRequest(BaseModel):
    """Данные регистрации. Пароль проверяется политикой в сервисе."""

    email: EmailStr
    password: str
    name: str | None = Field(default=None, max_length=200)


# Длиннее пароля не бывает; без потолка многомегабайтная строка шла в
# NFKC и Argon2 на каждый вход.
_PASSWORD_MAX = 1024


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=_PASSWORD_MAX)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=_PASSWORD_MAX)
    new_password: str = Field(max_length=_PASSWORD_MAX)


class TokenPair(BaseModel):
    """Пара токенов (внутренняя, между сервисом и роутом).

    Роут кладёт refresh в HttpOnly-cookie, а access — в тело ответа.
    token_type фиксирован для совместимости с OAuth2.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth-тип, не пароль)


class AccessToken(BaseModel):
    """Тело ответа auth: только access-токен. Refresh — в cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth-тип, не пароль)


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
