"""Юнит-тесты безопасности: Argon2id и JWT."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="x" * 64)  # type: ignore[call-arg]


def test_hash_differs_from_plain(settings: Settings) -> None:
    hashed = hash_password("S3cret!", settings)
    assert hashed != "S3cret!"
    assert hashed.startswith("$argon2id$")


def test_verify_correct_password(settings: Settings) -> None:
    hashed = hash_password("S3cret!", settings)
    assert verify_password(hashed, "S3cret!", settings) is True


def test_verify_wrong_password(settings: Settings) -> None:
    hashed = hash_password("S3cret!", settings)
    assert verify_password(hashed, "wrong", settings) is False


def test_same_password_different_hashes(
    settings: Settings,
) -> None:
    a = hash_password("S3cret!", settings)
    b = hash_password("S3cret!", settings)
    assert a != b


def test_access_token_roundtrip(settings: Settings) -> None:
    uid = uuid.uuid4()
    token = create_access_token(uid, settings)
    assert decode_token(token, settings, "access") == uid


def test_refresh_token_roundtrip(settings: Settings) -> None:
    uid = uuid.uuid4()
    token = create_refresh_token(uid, settings)
    assert decode_token(token, settings, "refresh") == uid


def test_wrong_token_type_rejected(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), settings)
    with pytest.raises(TokenError):
        decode_token(token, settings, "refresh")


def test_garbage_token_rejected(settings: Settings) -> None:
    with pytest.raises(TokenError):
        decode_token("not-a-jwt", settings, "access")


def test_expired_token_rejected(settings: Settings) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        decode_token(token, settings, "access")


def test_foreign_signature_rejected(settings: Settings) -> None:
    token = create_access_token(uuid.uuid4(), settings)
    other = Settings(secret_key="y" * 64)  # type: ignore[call-arg]
    with pytest.raises(TokenError):
        decode_token(token, other, "access")
