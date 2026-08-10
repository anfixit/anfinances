"""Расчёт «возраста денег» — четвёртое правило ВНБ.

Правило: жить на доход предыдущего месяца. Считаем, какую долю
расходов текущего месяца покрывает доход прошлого.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from app.domains.summary.service import SummaryService


class _StubRepo:
    """Отдаёт заранее заданные пары (доход, расход) по вызовам."""

    def __init__(self, pairs: list[tuple[Decimal, Decimal]]) -> None:
        self._pairs = pairs
        self.calls: list[tuple[datetime, datetime]] = []

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[Decimal, Decimal]:
        self.calls.append((date_from, date_to))
        return self._pairs[len(self.calls) - 1]


def _service(pairs: list[tuple[Decimal, Decimal]]) -> SummaryService:
    # Курсы в этом расчёте не участвуют: всё уже в рублях.
    return SummaryService(cast(Any, _StubRepo(pairs)), cast(Any, None))


async def test_covered_when_last_income_exceeds_current_expense() -> None:
    service = _service(
        [
            (Decimal("100000"), Decimal("0")),  # прошлый месяц: доход
            (Decimal("0"), Decimal("-60000")),  # текущий: расход
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.previous_month == "2026-07"
    assert result.current_month == "2026-08"
    assert result.previous_month_income_rub == Decimal("100000")
    assert result.current_month_expense_rub == Decimal("60000")
    assert result.coverage is not None
    assert round(result.coverage, 4) == Decimal("1.6667")
    assert result.is_covered is True


async def test_not_covered() -> None:
    service = _service(
        [
            (Decimal("50000"), Decimal("0")),
            (Decimal("0"), Decimal("-80000")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.is_covered is False


async def test_no_expenses_yet_gives_none_coverage() -> None:
    service = _service(
        [
            (Decimal("50000"), Decimal("0")),
            (Decimal("0"), Decimal("0")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert result.coverage is None
    # Нет трат — правило формально соблюдено.
    assert result.is_covered is True


async def test_no_income_last_month_is_not_covered() -> None:
    service = _service(
        [
            (Decimal("0"), Decimal("0")),
            (Decimal("0"), Decimal("-1000")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert result.coverage == Decimal("0")
    assert result.is_covered is False


async def test_january_looks_back_to_december() -> None:
    service = _service(
        [
            (Decimal("10"), Decimal("0")),
            (Decimal("0"), Decimal("-5")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 1, 15, tzinfo=UTC),
    )
    assert result.previous_month == "2025-12"
    assert result.current_month == "2026-01"


async def test_months_are_bounded_by_user_timezone() -> None:
    """Границы месяцев считаются в таймзоне пользователя, не в UTC."""
    repo = _StubRepo(
        [
            (Decimal("10"), Decimal("0")),
            (Decimal("0"), Decimal("-5")),
        ]
    )
    service = SummaryService(cast(Any, repo), cast(Any, None))
    await service.money_age(
        uuid.uuid4(),
        "Asia/Tashkent",
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    # Ташкент — UTC+5, значит локальное 1 августа 00:00 это
    # 31 июля 19:00 UTC.
    current_start = repo.calls[1][0]
    assert current_start == datetime(2026, 7, 31, 19, 0, tzinfo=UTC)


async def test_last_day_of_month_still_uses_current_month() -> None:
    service = _service(
        [
            (Decimal("100"), Decimal("0")),
            (Decimal("0"), Decimal("-50")),
        ]
    )
    result = await service.money_age(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 31, 20, tzinfo=UTC),
    )
    assert result.current_month == "2026-08"
    assert result.previous_month == "2026-07"
