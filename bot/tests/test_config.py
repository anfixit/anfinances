"""Разбор настроек бота из окружения."""

from typing import Any

import pytest
from pydantic import ValidationError

from anfinances_bot.config import BotSettings


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_ALLOWED_USER_IDS": "111",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
        "SINGLE_USER_EMAIL": "me@example.com",
        "SINGLE_USER_PASSWORD": "very-long-password-value",
        "BOT_DEFAULT_ACCOUNT_NAME": "Альфа",
    }
    base.update(overrides)
    return base


def _apply(monkeypatch: Any, **overrides: str) -> None:
    for key, value in _env(**overrides).items():
        monkeypatch.setenv(key, value)


def test_parses_single_allowed_id(monkeypatch: Any) -> None:
    _apply(monkeypatch)
    assert BotSettings().telegram_allowed_user_ids == frozenset({111})


def test_parses_comma_separated_ids(monkeypatch: Any) -> None:
    _apply(monkeypatch, TELEGRAM_ALLOWED_USER_IDS="111, 222,333")
    assert BotSettings().telegram_allowed_user_ids == frozenset(
        {111, 222, 333}
    )


def test_empty_allowlist_is_rejected(monkeypatch: Any) -> None:
    """Пустой белый список открыл бы бота всему интернету."""
    _apply(monkeypatch, TELEGRAM_ALLOWED_USER_IDS="")
    with pytest.raises(ValidationError):
        BotSettings()


def test_quiet_hours_default_and_parse(monkeypatch: Any) -> None:
    _apply(monkeypatch)
    assert BotSettings().bot_quiet_hours == (23, 9)

    monkeypatch.setenv("BOT_QUIET_HOURS", "0-7")
    assert BotSettings().bot_quiet_hours == (0, 7)


def test_bad_quiet_hours_rejected(monkeypatch: Any) -> None:
    _apply(monkeypatch, BOT_QUIET_HOURS="25-9")
    with pytest.raises(ValidationError):
        BotSettings()


def test_meeting_day_out_of_range_rejected(monkeypatch: Any) -> None:
    """29–31 числа есть не в каждом месяце — совещание бы пропускалось."""
    _apply(monkeypatch, BOT_BUDGET_MEETING_DAY="31")
    with pytest.raises(ValidationError):
        BotSettings()


def test_secrets_are_not_in_repr(monkeypatch: Any) -> None:
    _apply(monkeypatch)
    text = repr(BotSettings())
    assert "sk-ant-test" not in text
    assert "very-long-password-value" not in text
    assert "123:abc" not in text


def test_defaults_point_into_compose_network(monkeypatch: Any) -> None:
    _apply(monkeypatch)
    settings = BotSettings()
    assert settings.anfinances_base_url == "http://backend:8000/api/v1"
    assert settings.speech_model == "whisper-1"
