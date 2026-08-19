"""Правила проактивных сообщений.

Бот пишет первым в трёх случаях, и у каждого свой тормоз, иначе он
превращается в спам, а спам выключают вместе с ботом. Здесь только
решения «пора или нет» — сама отправка живёт в обработчиках.
"""

from datetime import datetime, timedelta

__all__ = [
    "REMINDER_SILENCE",
    "is_quiet",
    "should_hold_meeting",
    "should_remind",
    "should_warn_overspend",
]

REMINDER_SILENCE = timedelta(days=2)


def is_quiet(now: datetime, quiet_hours: tuple[int, int]) -> bool:
    """Попадает ли момент в часы тишины.

    Окно может идти через полночь: 23–9 — это вечер и утро, а не
    пустой интервал.
    """
    start, end = quiet_hours
    hour = now.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def should_remind(
    last_transaction_at: datetime | None,
    last_reminder_at: datetime | None,
    now: datetime,
    last_interaction_at: datetime | None = None,
) -> bool:
    """Напомнить, если операций не было двое суток и мы молчали.

    Разговор с ботом — тоже признак жизни: если она только что
    присылала выписку или спрашивала про остаток, напоминать «пару
    дней ничего не записывали» нелепо, даже когда записать ничего
    не получилось.
    """
    if (
        last_reminder_at is not None
        and now - last_reminder_at < REMINDER_SILENCE
    ):
        return False
    if (
        last_interaction_at is not None
        and now - last_interaction_at < REMINDER_SILENCE
    ):
        return False
    if last_transaction_at is None:
        return True
    return now - last_transaction_at >= REMINDER_SILENCE


def should_hold_meeting(
    now: datetime, day: int, last_meeting_at: datetime | None
) -> bool:
    """Бюджетное совещание — раз в месяц, в назначенный день."""
    if now.day != day:
        return False
    if last_meeting_at is None:
        return True
    return (last_meeting_at.year, last_meeting_at.month) != (
        now.year,
        now.month,
    )


def should_warn_overspend(
    category_id: str,
    month: str,
    already_warned: set[tuple[str, str]],
) -> bool:
    """Не чаще одного предупреждения на категорию за месяц."""
    return (category_id, month) not in already_warned
