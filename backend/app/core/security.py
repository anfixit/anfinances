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
        # iat в JWT — целые секунды. Отзыв сессий сравнивает точнее:
        # старый токен и новая пара после смены пароля бывают выпущены
        # в одну и ту же секунду.
        "iat_us": int(now.timestamp() * 1_000_000),
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
    subject, _ = decode_token_with_issued_at(token, settings, expected_type)
    return subject


def decode_token_with_issued_at(
    token: str,
    settings: Settings,
    expected_type: TokenType,
) -> tuple[uuid.UUID, datetime]:
    """То же, что decode_token, плюс момент выпуска (iat).

    Нужен, чтобы не принимать токены, выпущенные до того, как
    пользователь завершил все сессии.
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
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError) as exc:
        raise TokenError("Некорректный subject.") from exc

    precise = payload.get("iat_us")
    if isinstance(precise, int):
        return user_id, datetime.fromtimestamp(precise / 1_000_000, UTC)
    issued = payload.get("iat")
    if not isinstance(issued, int | float):
        raise TokenError("В токене нет времени выпуска.")
    # Токен без точного времени (выпущен до 27.11.2026) считаем
    # выпущенным в конце своей секунды: в спорной секунде — в пользу
    # токена, как было до появления отзыва сессий.
    return user_id, datetime.fromtimestamp(issued, UTC) + timedelta(
        microseconds=999_999
    )
