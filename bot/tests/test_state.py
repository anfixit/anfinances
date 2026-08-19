"""Отметки напоминаний переживают перезапуск бота."""

from datetime import UTC, datetime
from pathlib import Path

from anfinances_bot.state import BotState

WHEN = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)


def test_value_survives_restart(tmp_path: Path) -> None:
    """Деплой — это перезапуск, и он не повод напомнить заново."""
    path = tmp_path / "state.json"
    BotState(path).set("last_reminder_at", WHEN)
    assert BotState(path).get("last_reminder_at") == WHEN


def test_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert BotState(tmp_path / "нет.json").get("last_reminder_at") is None


def test_broken_file_is_ignored(tmp_path: Path) -> None:
    """Потерять отметку не страшно, упасть на старте — страшно."""
    path = tmp_path / "state.json"
    path.write_text("{это не json", "utf-8")
    assert BotState(path).get("last_reminder_at") is None


def test_unknown_keys_are_dropped(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('{"last_reminder_at": "x", "мусор": "y"}', "utf-8")
    state = BotState(path)
    assert state.get("last_reminder_at") is None
    state.set("last_meeting_at", WHEN)
    assert BotState(path).get("last_meeting_at") == WHEN


def test_directory_is_created(tmp_path: Path) -> None:
    path = tmp_path / "глубже" / "state.json"
    BotState(path).set("last_interaction_at", WHEN)
    assert path.exists()
