"""Кредит, возврат и корректировка — не доход и не трата.

Пока их не было, кредит на 430 000 и возвраты писались доходом, и
график за сентябрь показал +331 704 ₽ при настоящем −98 844 ₽.
Проверяется на настоящей сессии: всё это — SQL отчётов.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import ValidationFailedError
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.budgets.models import Budget
from app.domains.budgets.repository import SqlBudgetRepository
from app.domains.budgets.service import BudgetService
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService
from app.domains.summary.repository import SqlSummaryRepository
from app.domains.summary.service import SummaryService
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
)
from app.domains.transactions.service import TransactionService

TZ = "Europe/Moscow"
WHEN = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return Decimal(1)


def _tx(db_session: AsyncSession) -> TransactionService:
    return TransactionService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        cast(Any, _Currencies()),
        PayeeService(SqlPayeeRepository(db_session)),
    )


def _summary(db_session: AsyncSession) -> SummaryService:
    return SummaryService(
        SqlSummaryRepository(db_session), cast(Any, _Currencies())
    )


async def _category(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    name: str,
    kind: CategoryKind = CategoryKind.EXPENSE,
) -> uuid.UUID:
    category = Category(user_id=ledger["user"], name=name, kind=kind)
    db_session.add(category)
    await db_session.flush()
    return category.id


async def _create(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    kind: TransactionKind,
    amount: str,
    category_id: uuid.UUID | None = None,
) -> Transaction:
    return await _tx(db_session).create_transaction(
        ledger["user"],
        TransactionCreate(
            account_id=ledger["rub"],
            kind=cast(Any, kind),
            amount=Decimal(amount),
            date=WHEN,
            category_id=category_id,
        ),
    )


async def _cashflow(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> tuple[Decimal, Decimal]:
    result = await _summary(db_session).cashflow(
        ledger["user"], date(2026, 9, 1), date(2026, 9, 30), TZ
    )
    return result.income_rub, result.expense_rub


async def test_loan_is_money_but_not_income(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _create(db_session, ledger, TransactionKind.LOAN, "430000")
    assert tx.amount == Decimal("430000")
    assert await _cashflow(db_session, ledger) == (Decimal(0), Decimal(0))


async def test_refund_reduces_the_category_it_returns_to(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    pharmacy = await _category(db_session, ledger, "Лекарства")
    await _create(
        db_session, ledger, TransactionKind.EXPENSE, "1570", pharmacy
    )
    await _create(db_session, ledger, TransactionKind.REFUND, "1332", pharmacy)

    income, expense = await _cashflow(db_session, ledger)
    assert income == Decimal(0), "возврат не заработок"
    assert expense == Decimal("238")

    by_cat = await _summary(db_session).by_category(
        ledger["user"], "2026-09", TZ
    )
    assert by_cat.items[0].amount_rub == Decimal("238")


async def test_month_with_only_a_refund_is_not_a_spend(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Ловушка abs(): возврат без покупки в месяце выглядел тратой."""
    gear = await _category(db_session, ledger, "Активный отдых")
    await _create(db_session, ledger, TransactionKind.REFUND, "690.50", gear)

    by_cat = await _summary(db_session).by_category(
        ledger["user"], "2026-09", TZ
    )
    assert by_cat.items[0].amount_rub == Decimal("-690.50")


async def test_refund_puts_money_back_into_the_envelope(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    food = await _category(db_session, ledger, "Продукты")
    db_session.add(
        Budget(
            user_id=ledger["user"],
            month=date(2026, 9, 1),
            category_id=food,
            planned=Decimal("1000"),
        )
    )
    await db_session.flush()
    await _create(db_session, ledger, TransactionKind.EXPENSE, "700", food)
    await _create(db_session, ledger, TransactionKind.REFUND, "200", food)

    budgets = await BudgetService(
        SqlBudgetRepository(db_session), SqlCategoryRepository(db_session)
    ).list_budgets(ledger["user"], "2026-09", TZ)
    assert budgets[0].spent == Decimal("500")
    assert budgets[0].remaining == Decimal("500")


async def test_adjustment_keeps_its_sign_and_stays_out_of_reports(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _create(db_session, ledger, TransactionKind.ADJUSTMENT, "-9000")
    assert tx.amount == Decimal("-9000")
    assert await _cashflow(db_session, ledger) == (Decimal(0), Decimal(0))


def test_zero_adjustment_is_refused() -> None:
    with pytest.raises(ValidationError, match="ноль"):
        TransactionCreate(
            account_id=uuid.uuid4(),
            kind=TransactionKind.ADJUSTMENT,
            amount=Decimal(0),
            date=WHEN,
        )


def test_negative_amount_is_refused_outside_adjustments() -> None:
    with pytest.raises(ValidationError, match="больше нуля"):
        TransactionCreate(
            account_id=uuid.uuid4(),
            kind=TransactionKind.REFUND,
            amount=Decimal(-5),
            date=WHEN,
        )


async def test_loan_with_a_category_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    salary = await _category(
        db_session, ledger, "Зарплата", CategoryKind.INCOME
    )
    with pytest.raises(ValidationFailedError, match="нет категории"):
        await _create(db_session, ledger, TransactionKind.LOAN, "1", salary)


async def test_refund_without_a_category_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    with pytest.raises(ValidationFailedError, match="в какой"):
        await _create(db_session, ledger, TransactionKind.REFUND, "100")


async def test_refund_into_an_income_category_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    cashback = await _category(
        db_session, ledger, "Кэшбэк", CategoryKind.INCOME
    )
    with pytest.raises(ValidationFailedError, match="возврат"):
        await _create(
            db_session, ledger, TransactionKind.REFUND, "100", cashback
        )


async def test_income_relabelled_as_loan_keeps_money_drops_category(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Ровно та ошибка: кредит на 430 000 записан доходом."""
    fix = await _category(
        db_session, ledger, "Корректировка баланса", CategoryKind.INCOME
    )
    tx = await _create(
        db_session, ledger, TransactionKind.INCOME, "430000", fix
    )
    tx = await _tx(db_session).update_transaction(
        tx.id, ledger["user"], TransactionUpdate(kind=TransactionKind.LOAN)
    )
    assert tx.kind == TransactionKind.LOAN
    assert tx.amount == Decimal("430000")
    assert tx.amount_rub == Decimal("430000")
    assert tx.category_id is None
    assert await _cashflow(db_session, ledger) == (Decimal(0), Decimal(0))


async def test_income_relabelled_as_refund_needs_an_expense_category(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    fix = await _category(
        db_session, ledger, "Корректировка баланса", CategoryKind.INCOME
    )
    pharmacy = await _category(db_session, ledger, "Лекарства")
    tx = await _create(db_session, ledger, TransactionKind.INCOME, "1332", fix)
    service = _tx(db_session)

    # Доходная категория возврату не подходит.
    with pytest.raises(ValidationFailedError):
        await service.update_transaction(
            tx.id,
            ledger["user"],
            TransactionUpdate(kind=TransactionKind.REFUND),
        )

    tx = await service.update_transaction(
        tx.id,
        ledger["user"],
        TransactionUpdate(kind=TransactionKind.REFUND, category_id=pharmacy),
    )
    assert tx.kind == TransactionKind.REFUND
    assert tx.amount == Decimal("1332")
    assert tx.category_id == pharmacy


async def test_expense_relabelled_as_adjustment_stays_negative(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    fix = await _category(db_session, ledger, "Корректировка")
    tx = await _create(
        db_session, ledger, TransactionKind.EXPENSE, "9000", fix
    )
    tx = await _tx(db_session).update_transaction(
        tx.id,
        ledger["user"],
        TransactionUpdate(kind=TransactionKind.ADJUSTMENT),
    )
    assert tx.amount == Decimal("-9000")
    assert tx.category_id is None


async def test_editing_a_negative_adjustment_keeps_its_direction(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _create(db_session, ledger, TransactionKind.ADJUSTMENT, "-500")
    tx = await _tx(db_session).update_transaction(
        tx.id, ledger["user"], TransactionUpdate(amount=Decimal("700"))
    )
    assert tx.amount == Decimal("-700")
