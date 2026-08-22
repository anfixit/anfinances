"""Сверка счёта с выпиской банка.

Проверяется на настоящей сессии: расхождение считается суммой по
операциям до даты, а это SQL. На заглушке проверялась бы арифметика,
которой тут и нет.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import ValidationFailedError
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService
from app.domains.reconciliation.repository import (
    SqlReconciliationRepository,
)
from app.domains.reconciliation.schemas import ReconcileRequest
from app.domains.reconciliation.service import ReconciliationService
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.service import TransactionService

EARLY = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
LATE = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
AFTER = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return Decimal(1)


def _service(db_session: AsyncSession) -> ReconciliationService:
    transactions = TransactionService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        _Currencies(),  # type: ignore[arg-type]
        PayeeService(SqlPayeeRepository(db_session)),
    )
    return ReconciliationService(
        SqlReconciliationRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        transactions,
    )


async def _spend(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    amount: Decimal,
    when: datetime,
) -> Transaction:
    tx = Transaction(
        user_id=ledger["user"],
        account_id=ledger["rub"],
        kind=TransactionKind.EXPENSE,
        amount=-abs(amount),
        currency_code="RUB",
        amount_rub=-abs(amount),
        exchange_rate=Decimal(1),
        date=when,
    )
    db_session.add(tx)
    await db_session.flush()
    return tx


def _request(balance: str, when: datetime, **over: object) -> ReconcileRequest:
    return ReconcileRequest(
        statement_balance=Decimal(balance), date=when, **over
    )


async def test_matching_balance_reconciles_without_adjustment(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)

    row = await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    assert row.adjustment_transaction_id is None
    assert row.computed_balance == Decimal("-300")


async def test_difference_is_refused_until_asked_to_adjust(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Сверка должна показать расхождение, а не подогнать остаток."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)

    with pytest.raises(ValidationFailedError) as exc:
        await service.reconcile(
            ledger["rub"], ledger["user"], _request("-500", LATE)
        )
    assert "-200" in str(exc.value)


async def test_adjustment_closes_the_gap(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)

    row = await service.reconcile(
        ledger["rub"],
        ledger["user"],
        _request("-500", LATE, adjust=True),
    )
    assert row.adjustment_transaction_id is not None

    # После корректировки остаток сходится с банком.
    again = await service.preview(
        ledger["rub"], ledger["user"], _request("-500", LATE)
    )
    assert again.difference == Decimal(0)


async def test_bank_richer_than_records_creates_income(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Не хватает дохода — корректировка приходом, а не расходом."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)

    row = await service.reconcile(
        ledger["rub"],
        ledger["user"],
        _request("-100", LATE, adjust=True),
    )
    tx = await db_session.get(Transaction, row.adjustment_transaction_id)
    assert tx is not None
    assert tx.kind == TransactionKind.INCOME
    assert tx.amount == Decimal("200")


async def test_operations_after_the_date_are_not_counted(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Сверяют на дату выписки, а не на сегодня."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    await _spend(db_session, ledger, Decimal("999"), AFTER)

    result = await service.preview(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    assert result.computed_balance == Decimal("-300")
    assert result.difference == Decimal(0)


async def test_reconciled_operations_are_stamped(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    covered = await _spend(db_session, ledger, Decimal("300"), EARLY)
    later = await _spend(db_session, ledger, Decimal("50"), AFTER)

    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    await db_session.refresh(covered)
    await db_session.refresh(later)
    assert covered.reconciled_at is not None
    assert later.reconciled_at is None, "операция после даты не сверена"


async def test_second_reconciliation_counts_only_new_operations(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Второй раз под отметку попадает только то, что добавилось."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )

    await _spend(db_session, ledger, Decimal("50"), AFTER)
    result = await service.preview(
        ledger["rub"], ledger["user"], _request("-350", AFTER)
    )
    assert result.unreconciled_count == 1


async def test_initial_balance_is_part_of_the_computed_balance(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Счёт заводят с остатком; забыть его — вечное расхождение."""
    account = await SqlAccountRepository(db_session).get(
        ledger["rub"], ledger["user"]
    )
    assert account is not None
    account.initial_balance = Decimal("1000")
    await db_session.flush()

    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    result = await service.preview(
        ledger["rub"], ledger["user"], _request("700", LATE)
    )
    assert result.computed_balance == Decimal("700")
    assert result.difference == Decimal(0)


async def test_adjustment_lands_in_the_given_category(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    category = Category(
        user_id=ledger["user"],
        name="Корректировка баланса",
        kind=CategoryKind.EXPENSE,
    )
    db_session.add(category)
    await db_session.flush()

    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    row = await service.reconcile(
        ledger["rub"],
        ledger["user"],
        _request(
            "-500", LATE, adjust=True, adjustment_category_id=category.id
        ),
    )
    tx = await db_session.get(Transaction, row.adjustment_transaction_id)
    assert tx is not None
    assert tx.category_id == category.id
