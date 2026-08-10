"""Общие фикстуры тестов бота."""

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Настройки кэшируются — сбрасываем между тестами."""
    from anfinances_bot.config import get_bot_settings

    get_bot_settings.cache_clear()
