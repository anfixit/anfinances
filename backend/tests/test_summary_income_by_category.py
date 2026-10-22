"""Доходы месяца по категориям — только заработанное.

Ассистент планирует погашение долгов от дохода. Если в доход
попадёт полученный кредит или возврат с Ozon, план поверит в
деньги, которых владелец не зарабатывал. Проверяется на настоящей
сессии: это SQL отчёта.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService
from app.domains.summary.repository import SqlSummaryRepository
from app.domains.summary.service import SummaryService
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.schemas import TransactionCreate, TransferCreate
from app.domains.transactions.service import (
    TransactionService,
    TransferService,
)

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
    kind: CategoryKind,
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
    when: datetime = WHEN,
) -> None:
    await _tx(db_session).create_transaction(
        ledger["user"],
        TransactionCreate(
            account_id=ledger["rub"],
            kind=cast(Any, kind),
            amount=Decimal(amount),
            date=when,
            category_id=category_id,
        ),
    )


async def test_only_earned_money_counts_as_income(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    salary = await _category(
        db_session, ledger, "Зарплата", CategoryKind.INCOME
    )
    freelance = await _category(
        db_session, ledger, "Фриланс", CategoryKind.INCOME
    )
    pharmacy = await _category(
        db_session, ledger, "Лекарства", CategoryKind.EXPENSE
    )

    await _create(db_session, ledger, TransactionKind.INCOME, "120000", salary)
    await _create(
        db_session, ledger, TransactionKind.INCOME, "15000.50", freelance
    )
    await _create(db_session, ledger, TransactionKind.INCOME, "5000", salary)
    # Деньги на счёт, но не заработок.
    await _create(db_session, ledger, TransactionKind.LOAN, "430000")
    await _create(
        db_session, ledger, TransactionKind.EXPENSE, "2000", pharmacy
    )
    await _create(db_session, ledger, TransactionKind.REFUND, "1332", pharmacy)
    await _create(db_session, ledger, TransactionKind.ADJUSTMENT, "9000")
    await TransferService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        cast(Any, _Currencies()),
    ).create_transfer(
        ledger["user"],
        TransferCreate(
            from_account_id=ledger["rub"],
            to_account_id=ledger["uzs"],
            amount_from=Decimal("1000"),
            amount_to=Decimal("1000"),
            date=WHEN,
        ),
    )

    result = await _summary(db_session).income_by_category(
        ledger["user"], "2026-09", TZ
    )

    assert result.month == "2026-09"
    assert [(i.category_id, i.amount_rub) for i in result.items] == [
        (salary, Decimal("125000")),
        (freelance, Decimal("15000.50")),
    ]
    assert result.total_rub == Decimal("140000.50")


async def test_month_is_cut_in_the_user_timezone(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Зарплата в 01:00 по Москве 1-го — уже новый месяц, хотя в UTC
    ещё предыдущий."""
    salary = await _category(
        db_session, ledger, "Зарплата", CategoryKind.INCOME
    )
    # 31 августа 22:00 UTC = 1 сентября 01:00 MSK.
    await _create(
        db_session,
        ledger,
        TransactionKind.INCOME,
        "100",
        salary,
        when=datetime(2026, 8, 31, 22, 0, tzinfo=UTC),
    )
    # 30 сентября 22:00 UTC = 1 октября 01:00 MSK.
    await _create(
        db_session,
        ledger,
        TransactionKind.INCOME,
        "7",
        salary,
        when=datetime(2026, 9, 30, 22, 0, tzinfo=UTC),
    )

    september = await _summary(db_session).income_by_category(
        ledger["user"], "2026-09", TZ
    )
    october = await _summary(db_session).income_by_category(
        ledger["user"], "2026-10", TZ
    )

    assert september.total_rub == Decimal("100")
    assert october.total_rub == Decimal("7")


async def test_quiet_month_is_empty_not_an_error(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    result = await _summary(db_session).income_by_category(
        ledger["user"], "2026-09", TZ
    )
    assert result.items == []
    assert result.total_rub == Decimal(0)
