"""Timezone-aware границы пользовательских периодов."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

__all__ = [
    "DEFAULT_TIMEZONE",
    "date_range_utc",
    "month_bounds_utc",
    "recent_full_months_utc",
]

DEFAULT_TIMEZONE = "Europe/Moscow"


def date_range_utc(
    date_from: date,
    date_to: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    """Вернуть UTC-границы локального диапазона дат.

    Правая граница исключительная: начало дня после ``date_to``.
    """
    timezone = ZoneInfo(timezone_name)
    start_local = datetime.combine(date_from, time.min, timezone)
    end_local = datetime.combine(
        date_to + timedelta(days=1),
        time.min,
        timezone,
    )
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def month_bounds_utc(
    value: date,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    """Вернуть UTC-границы локального календарного месяца."""
    next_month = _shift_month(value.year, value.month, 1)
    return date_range_utc(
        date(value.year, value.month, 1),
        date(next_month.year, next_month.month, 1) - timedelta(days=1),
        timezone_name,
    )


def recent_full_months_utc(
    months: int,
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Вернуть UTC-окно последних полных локальных месяцев."""
    timezone = ZoneInfo(timezone_name)
    current = (now or datetime.now(UTC)).astimezone(timezone)
    end_local = datetime(
        current.year,
        current.month,
        1,
        tzinfo=timezone,
    )
    start_month = _shift_month(current.year, current.month, -months)
    start_local = datetime(
        start_month.year,
        start_month.month,
        1,
        tzinfo=timezone,
    )
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _shift_month(year: int, month: int, offset: int) -> date:
    index = year * 12 + month - 1 + offset
    shifted_year, shifted_month = divmod(index, 12)
    return date(shifted_year, shifted_month + 1, 1)
