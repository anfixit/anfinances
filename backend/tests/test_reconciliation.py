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

from app.core.enums import TransactionKind
from app.core.exceptions import ValidationFailedError
from app.domains.accounts.repository import SqlAccountRepository
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
from app.domains.transactions.schemas import TransactionUpdate
from app.domains.transactions.service import TransactionService

EARLY = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
LATE = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
AFTER = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return Decimal(1)


def _transactions(db_session: AsyncSession) -> TransactionService:
    return TransactionService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        _Currencies(),  # type: ignore[arg-type]
        PayeeService(SqlPayeeRepository(db_session)),
    )


def _service(db_session: AsyncSession) -> ReconciliationService:
    return ReconciliationService(
        SqlReconciliationRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        _transactions(db_session),
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


async def test_gap_is_closed_by_an_adjustment_not_income(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Каждая сверка раньше рисовала в графике выдуманный доход."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)

    row = await service.reconcile(
        ledger["rub"],
        ledger["user"],
        _request("-100", LATE, adjust=True),
    )
    tx = await db_session.get(Transaction, row.adjustment_transaction_id)
    assert tx is not None
    assert tx.kind == TransactionKind.ADJUSTMENT
    assert tx.amount == Decimal("200")
    assert tx.category_id is None


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


async def test_repeated_adjustment_click_does_not_adjust_twice(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Второй клик «Закрыть корректировкой» видит уже нулевую разницу
    и отказывается, вместо того чтобы закрыть её ещё раз."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    request = _request(
        "-500", LATE, adjust=True, expected_difference=Decimal("-200")
    )

    await service.reconcile(ledger["rub"], ledger["user"], request)
    with pytest.raises(ValidationFailedError, match="изменился"):
        await service.reconcile(ledger["rub"], ledger["user"], request)

    result = await service.preview(
        ledger["rub"], ledger["user"], _request("-500", LATE)
    )
    assert result.difference == Decimal(0)


async def test_adjustment_refused_when_balance_moved_since_preview(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Между проверкой и подтверждением добавилась операция — закрывать
    показанную разницу уже нельзя."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    await _spend(db_session, ledger, Decimal("50"), EARLY)

    with pytest.raises(ValidationFailedError, match="-150"):
        await service.reconcile(
            ledger["rub"],
            ledger["user"],
            _request(
                "-500", LATE, adjust=True, expected_difference=Decimal("-200")
            ),
        )


async def test_adjustment_before_last_reconciliation_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Корректировка задним числом сдвинула бы остаток и в прошлой
    сверке, которая уже сошлась."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )

    with pytest.raises(ValidationFailedError, match="уже сверен"):
        await service.reconcile(
            ledger["rub"],
            ledger["user"],
            _request("-400", EARLY, adjust=True),
        )


async def test_zero_difference_reconciliation_may_be_backdated(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Без корректировки остаток не двигается — сверить прошлую выписку
    после свежей можно."""
    service = _service(db_session)
    await _spend(db_session, ledger, Decimal("300"), EARLY)
    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    row = await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", EARLY)
    )
    assert row.adjustment_transaction_id is None


async def test_editing_amount_clears_the_reconciled_mark(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Сверенная операция с новой суммой — уже не та, что сходилась."""
    service = _service(db_session)
    tx = await _spend(db_session, ledger, Decimal("300"), EARLY)
    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    await db_session.refresh(tx)
    assert tx.reconciled_at is not None

    transactions = _transactions(db_session)
    await transactions.update_transaction(
        tx.id, ledger["user"], TransactionUpdate(comment="кофе")
    )
    assert tx.reconciled_at is not None, "комментарий остаток не трогает"

    await transactions.update_transaction(
        tx.id, ledger["user"], TransactionUpdate(amount=Decimal("350"))
    )
    assert tx.reconciled_at is None


async def test_moving_to_another_account_clears_the_reconciled_mark(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    tx = await _spend(db_session, ledger, Decimal("300"), EARLY)
    await service.reconcile(
        ledger["rub"], ledger["user"], _request("-300", LATE)
    )
    await db_session.refresh(tx)

    await _transactions(db_session).update_transaction(
        tx.id, ledger["user"], TransactionUpdate(account_id=ledger["uzs"])
    )
    assert tx.reconciled_at is None


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
