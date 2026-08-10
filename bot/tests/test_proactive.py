"""Тормоза проактивных сценариев."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from anfinances_bot.proactive import (
    is_quiet,
    should_hold_meeting,
    should_remind,
    should_warn_overspend,
)

MSK = ZoneInfo("Europe/Moscow")


def _at(hour: int, day: int = 10) -> datetime:
    return datetime(2026, 8, day, hour, 0, tzinfo=MSK)


def test_quiet_window_wraps_midnight() -> None:
    assert is_quiet(_at(23), (23, 9)) is True
    assert is_quiet(_at(3), (23, 9)) is True
    assert is_quiet(_at(8), (23, 9)) is True
    assert is_quiet(_at(9), (23, 9)) is False
    assert is_quiet(_at(15), (23, 9)) is False


def test_quiet_window_without_wrap() -> None:
    assert is_quiet(_at(2), (1, 5)) is True
    assert is_quiet(_at(6), (1, 5)) is False


def test_reminder_after_two_days_of_silence() -> None:
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(days=3),
            last_reminder_at=None,
            now=now,
        )
        is True
    )


def test_no_reminder_if_recent_transaction() -> None:
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(hours=5),
            last_reminder_at=None,
            now=now,
        )
        is False
    )


def test_no_repeat_reminder_within_two_days() -> None:
    """Напомнили вчера — сегодня молчим, даже если операций всё нет."""
    now = _at(12)
    assert (
        should_remind(
            last_transaction_at=now - timedelta(days=5),
            last_reminder_at=now - timedelta(hours=6),
            now=now,
        )
        is False
    )


def test_reminder_when_there_were_never_transactions() -> None:
    now = _at(12)
    assert (
        should_remind(last_transaction_at=None, last_reminder_at=None, now=now)
        is True
    )


def test_meeting_on_configured_day_once() -> None:
    now = _at(12, day=1)
    assert should_hold_meeting(now, day=1, last_meeting_at=None) is True
    assert should_hold_meeting(now, day=1, last_meeting_at=now) is False


def test_no_meeting_on_other_days() -> None:
    assert (
        should_hold_meeting(_at(12, day=2), day=1, last_meeting_at=None)
        is False
    )


def test_meeting_next_month_allowed() -> None:
    previous = datetime(2026, 7, 1, 12, tzinfo=MSK)
    now = datetime(2026, 8, 1, 12, tzinfo=MSK)
    assert should_hold_meeting(now, day=1, last_meeting_at=previous) is True


def test_meeting_a_year_later_on_the_same_month_allowed() -> None:
    """Сравнение только по месяцу пропустило бы год."""
    previous = datetime(2025, 8, 1, 12, tzinfo=MSK)
    now = datetime(2026, 8, 1, 12, tzinfo=MSK)
    assert should_hold_meeting(now, day=1, last_meeting_at=previous) is True


def test_overspend_warned_once_per_category_per_month() -> None:
    warned: set[tuple[str, str]] = set()
    assert should_warn_overspend("c-1", "2026-08", warned) is True
    warned.add(("c-1", "2026-08"))
    assert should_warn_overspend("c-1", "2026-08", warned) is False
    assert should_warn_overspend("c-1", "2026-09", warned) is True
    assert should_warn_overspend("c-2", "2026-08", warned) is True
