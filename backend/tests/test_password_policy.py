"""Тесты офлайн-политики паролей."""

import pytest

from app.config import Settings
from app.core.password_policy import (
    PasswordPolicyError,
    normalize_password,
    validate_password,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="x" * 64)  # type: ignore[call-arg]


def test_strong_long_passphrase_ok(settings: Settings) -> None:
    validate_password("fluffy-zebra-canyon-marble-97", settings)


def test_too_short_rejected(settings: Settings) -> None:
    with pytest.raises(PasswordPolicyError, match="короче"):
        validate_password("Short1!aaaa", settings)


def test_too_long_rejected(settings: Settings) -> None:
    with pytest.raises(PasswordPolicyError, match="длиннее"):
        validate_password("a" * 200, settings)


def test_blocklisted_rejected(settings: Settings) -> None:
    with pytest.raises(PasswordPolicyError, match="известен"):
        validate_password("correcthorsebatterystaple", settings)


def test_weak_but_long_rejected(settings: Settings) -> None:
    with pytest.raises(PasswordPolicyError, match="слабый"):
        validate_password("aaaaaaaaaaaaaaaa", settings)


def test_similar_to_user_input_rejected(
    settings: Settings,
) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password(
            "anfisaanfisaanfisa",
            settings,
            user_inputs=["anfisa", "anfisa@mail.ru"],
        )


def test_nfkc_normalization() -> None:
    raw = "café\u0301"
    assert normalize_password(raw) == normalize_password(
        normalize_password(raw)
    )
