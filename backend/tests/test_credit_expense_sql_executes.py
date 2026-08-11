"""Запросы расходной проекции должны выполняться, а не только строиться.

Существующие тесты этой проекции подсовывают вместо сессии
``AsyncMock``: SQL в них никогда не компилируется, поэтому запрос с
неразрешимым JOIN проходил их и падал уже на проде. Здесь запросы
выполняются на настоящей сессии — компиляция входит в проверку.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.credits.expense_projection import (
    credit_expense_total_rub,
    credit_expenses_by_category_rub,
)

DATE_FROM = datetime(2026, 1, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 2, 1, tzinfo=UTC)


async def test_total_query_compiles_and_runs(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    total = await credit_expense_total_rub(
        db_session, ledger["user"], DATE_FROM, DATE_TO
    )
    assert total == Decimal(0)


async def test_by_category_query_compiles_and_runs(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    rows = await credit_expenses_by_category_rub(
        db_session,
        ledger["user"],
        date_from=DATE_FROM,
        date_to=DATE_TO,
    )
    assert rows == {}


async def test_by_category_without_date_bounds_runs(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Границы дат необязательны — без них запрос тоже должен собраться."""
    rows = await credit_expenses_by_category_rub(db_session, ledger["user"])
    assert rows == {}
