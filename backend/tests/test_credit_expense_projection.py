"""Тесты расходной проекции кредитных платежей."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.core.enums import TransactionKind
from app.domains.budgets.repository import SqlBudgetRepository
from app.domains.credits.expense_projection import (
    credit_expense_total_rub,
    credit_expenses_by_category_rub,
)
from app.domains.summary.repository import SqlSummaryRepository

USER = uuid.uuid4()
DATE_FROM = datetime(2026, 1, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 2, 1, tzinfo=UTC)


class FakeResult:
    def __init__(
        self,
        rows: list[tuple[object, Decimal]] | None = None,
        scalar: Decimal | None = None,
    ) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def all(self) -> list[tuple[object, Decimal]]:
        return self._rows

    def scalar_one(self) -> Decimal:
        if self._scalar is None:
            raise AssertionError("Scalar result was not configured.")
        return self._scalar


async def test_credit_expense_total_returns_signed_rub_amount() -> None:
    session = AsyncMock()
    session.execute.return_value = FakeResult(scalar=Decimal("-7979.81"))

    total = await credit_expense_total_rub(
        session,
        USER,
        DATE_FROM,
        DATE_TO,
    )

    assert total == Decimal("-7979.81")
    session.execute.assert_awaited_once()


async def test_credit_expenses_are_grouped_by_category() -> None:
    interest_category = uuid.uuid4()
    fee_category = uuid.uuid4()
    session = AsyncMock()
    session.execute.return_value = FakeResult(
        rows=[
            (interest_category, Decimal("-7979.81")),
            (fee_category, Decimal("-100")),
            (None, Decimal("-50")),
        ]
    )

    spending = await credit_expenses_by_category_rub(
        session,
        USER,
        date_from=DATE_FROM,
        date_to=DATE_TO,
    )

    assert spending == {
        interest_category: Decimal("-7979.81"),
        fee_category: Decimal("-100"),
        None: Decimal("-50"),
    }


async def test_summary_cashflow_adds_credit_expenses(monkeypatch) -> None:
    session = AsyncMock()
    session.execute.return_value = FakeResult(
        rows=[
            (TransactionKind.INCOME, Decimal("5000")),
            (TransactionKind.EXPENSE, Decimal("-3000")),
        ]
    )
    projection = AsyncMock(return_value=Decimal("-1000"))
    monkeypatch.setattr(
        "app.domains.summary.repository.credit_expense_total_rub",
        projection,
    )

    income, expense = await SqlSummaryRepository(session).cashflow(
        USER,
        DATE_FROM,
        DATE_TO,
    )

    assert income == Decimal("5000")
    assert expense == Decimal("-4000")


async def test_summary_merges_credit_expenses_by_category(
    monkeypatch,
) -> None:
    category = uuid.uuid4()
    fee_category = uuid.uuid4()
    session = AsyncMock()
    session.execute.return_value = FakeResult(
        rows=[(category, Decimal("-300"))]
    )
    projection = AsyncMock(
        return_value={
            category: Decimal("-100"),
            fee_category: Decimal("-50"),
        }
    )
    monkeypatch.setattr(
        "app.domains.summary.repository.credit_expenses_by_category_rub",
        projection,
    )

    rows = await SqlSummaryRepository(session).spending_by_category(
        USER,
        DATE_FROM,
        DATE_TO,
    )

    assert dict(rows) == {
        category: Decimal("-400"),
        fee_category: Decimal("-50"),
    }


async def test_budget_ignores_uncategorized_credit_expense(
    monkeypatch,
) -> None:
    category = uuid.uuid4()
    session = AsyncMock()
    session.execute.return_value = FakeResult(
        rows=[(category, Decimal("-300"))]
    )
    projection = AsyncMock(
        return_value={
            category: Decimal("-100"),
            None: Decimal("-50"),
        }
    )
    monkeypatch.setattr(
        "app.domains.budgets.repository.credit_expenses_by_category_rub",
        projection,
    )

    spending = await SqlBudgetRepository(session).spent_by_category(
        USER,
        DATE_FROM,
        DATE_TO,
    )

    assert spending == {category: Decimal("-400")}
