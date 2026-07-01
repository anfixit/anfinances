"""Тесты преобразования локальных периодов в UTC."""

from datetime import UTC, date, datetime

from app.core.datetime import (
    date_range_utc,
    month_bounds_utc,
    recent_full_months_utc,
)


def test_date_range_uses_user_timezone() -> None:
    start, end = date_range_utc(
        date(2026, 7, 1),
        date(2026, 7, 1),
        "Europe/Samara",
    )

    assert start == datetime(2026, 6, 30, 20, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, 20, tzinfo=UTC)


def test_month_bounds_use_user_timezone() -> None:
    start, end = month_bounds_utc(
        date(2026, 7, 1),
        "Asia/Tashkent",
    )

    assert start == datetime(2026, 6, 30, 19, tzinfo=UTC)
    assert end == datetime(2026, 7, 31, 19, tzinfo=UTC)


def test_month_bounds_handle_daylight_saving_time() -> None:
    start, end = month_bounds_utc(
        date(2026, 3, 1),
        "Europe/Berlin",
    )

    assert start == datetime(2026, 2, 28, 23, tzinfo=UTC)
    assert end == datetime(2026, 3, 31, 22, tzinfo=UTC)


def test_recent_full_months_use_local_calendar() -> None:
    start, end = recent_full_months_utc(
        3,
        "Europe/Samara",
        now=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )

    assert start == datetime(2026, 3, 31, 20, tzinfo=UTC)
    assert end == datetime(2026, 6, 30, 20, tzinfo=UTC)
