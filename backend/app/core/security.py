"""Безопасность: хеширование паролей (Argon2id) и JWT (PyJWT).

Чистые функции без БД и HTTP. Параметры берутся из настроек:
Argon2id — §8.1 стандартов (time_cost=2, memory_cost=64 МиБ),
JWT — секрет и сроки жизни из config.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import Settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Невалидный, просроченный или подменённый токен."""


def _hasher(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=2,
    )


def hash_password(plain: str, settings: Settings) -> str:
    """Захешировать пароль алгоритмом Argon2id."""
    return _hasher(settings).hash(plain)


def verify_password(hashed: str, plain: str, settings: Settings) -> bool:
    """Проверить пароль. Возвращает False при несовпадении."""
    try:
        return _hasher(settings).verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str, settings: Settings) -> bool:
    """True, если хеш создан со старыми параметрами Argon2id.

    Позволяет прозрачно переусиливать пароль при логине, когда
    параметры в настройках изменились.
    """
    return _hasher(settings).check_needs_rehash(hashed)


def _create_token(
    subject: uuid.UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    settings: Settings,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(subject: uuid.UUID, settings: Settings) -> str:
    """Создать короткоживущий access-токен."""
    return _create_token(
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        settings,
    )


def create_refresh_token(subject: uuid.UUID, settings: Settings) -> str:
    """Создать долгоживущий refresh-токен."""
    return _create_token(
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        settings,
    )


def decode_token(
    token: str,
    settings: Settings,
    expected_type: TokenType,
) -> uuid.UUID:
    """Проверить токен и вернуть subject (user_id).

    Raises:
        TokenError: токен просрочен, повреждён, либо его тип
            не совпадает с expected_type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Невалидный токен.") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Неверный тип токена.")

    subject = payload.get("sub")
    if not subject:
        raise TokenError("В токене отсутствует subject.")

    try:
        return uuid.UUID(subject)
    except (ValueError, TypeError) as exc:
        raise TokenError("Некорректный subject.") from exc
