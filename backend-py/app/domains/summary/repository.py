"""Агрегатные read-only запросы для домена summary."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.accounts.models import Account
from app.domains.transactions.models import Transaction

__all__ = ["SummaryRepository", "SqlSummaryRepository"]


class SummaryRepository(Protocol):
    async def active_accounts(self, user_id: uuid.UUID) -> list[Account]: ...

    async def balances_by_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]: ...

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[Decimal, Decimal]: ...

    async def spending_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID | None, Decimal]]: ...


class SqlSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def active_accounts(self, user_id: uuid.UUID) -> list[Account]:
        result = await self._session.execute(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.is_archived.is_(False),
            )
            .order_by(Account.sort_order, Account.name)
        )
        return list(result.scalars().all())

    async def balances_by_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]:
        # Σ amount по каждому счёту (знак уже заложен в данных).
        result = await self._session.execute(
            select(
                Transaction.account_id,
                func.coalesce(func.sum(Transaction.amount), Decimal(0)),
            )
            .where(Transaction.user_id == user_id)
            .group_by(Transaction.account_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[Decimal, Decimal]:
        # Доход и расход в рублях за период; переводы исключены.
        result = await self._session.execute(
            select(
                Transaction.kind,
                func.coalesce(func.sum(Transaction.amount_rub), Decimal(0)),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.date >= date_from,
                Transaction.date <= date_to,
                Transaction.kind != TransactionKind.TRANSFER,
            )
            .group_by(Transaction.kind)
        )
        income = Decimal(0)
        expense = Decimal(0)
        for kind, total in result.all():
            if kind == TransactionKind.INCOME:
                income = total
            elif kind == TransactionKind.EXPENSE:
                expense = total
        return income, expense

    async def spending_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID | None, Decimal]]:
        # Только расходы за период, сгруппированные по категории.
        result = await self._session.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_rub), Decimal(0)),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.date >= date_from,
                Transaction.date <= date_to,
                Transaction.kind == TransactionKind.EXPENSE,
            )
            .group_by(Transaction.category_id)
        )
        return [(row[0], row[1]) for row in result.all()]
