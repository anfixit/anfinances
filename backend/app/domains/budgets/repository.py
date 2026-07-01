"""Доступ к БД для домена budgets.

Содержит только запросы, без бизнес-логики и без commit —
транзакцией управляет роут (ADR-013). Агрегаты по расходам берутся
из ``transactions`` по запечённому ``amount_rub`` (расход хранится
со знаком минус — Стратегия А).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.budgets.models import Budget
from app.domains.transactions.models import Transaction

__all__ = ["BudgetRepository", "SqlBudgetRepository"]


class BudgetRepository(Protocol):
    async def list_by_month(
        self, user_id: uuid.UUID, month: date
    ) -> list[Budget]: ...

    async def get(
        self, budget_id: uuid.UUID, user_id: uuid.UUID
    ) -> Budget | None: ...

    async def get_by_month_category(
        self,
        user_id: uuid.UUID,
        month: date,
        category_id: uuid.UUID,
    ) -> Budget | None: ...

    async def add(self, budget: Budget) -> Budget: ...

    async def delete(self, budget: Budget) -> None: ...

    async def spent_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> dict[uuid.UUID, Decimal]: ...

    async def planned_before(
        self, user_id: uuid.UUID, month: date
    ) -> dict[uuid.UUID, Decimal]: ...

    async def spent_before(
        self, user_id: uuid.UUID, before: datetime
    ) -> dict[uuid.UUID, Decimal]: ...


class SqlBudgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_month(
        self, user_id: uuid.UUID, month: date
    ) -> list[Budget]:
        result = await self._session.execute(
            select(Budget)
            .where(
                Budget.user_id == user_id,
                Budget.month == month,
            )
            .order_by(Budget.created_at)
        )
        return list(result.scalars().all())

    async def get(
        self, budget_id: uuid.UUID, user_id: uuid.UUID
    ) -> Budget | None:
        result = await self._session.execute(
            select(Budget).where(
                Budget.id == budget_id,
                Budget.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_month_category(
        self,
        user_id: uuid.UUID,
        month: date,
        category_id: uuid.UUID,
    ) -> Budget | None:
        result = await self._session.execute(
            select(Budget).where(
                Budget.user_id == user_id,
                Budget.month == month,
                Budget.category_id == category_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, budget: Budget) -> Budget:
        self._session.add(budget)
        await self._session.flush()
        return budget

    async def delete(self, budget: Budget) -> None:
        await self._session.delete(budget)

    async def spent_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> dict[uuid.UUID, Decimal]:
        result = await self._session.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_rub), Decimal(0)),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.EXPENSE,
                Transaction.date >= date_from,
                Transaction.date < date_to,
            )
            .group_by(Transaction.category_id)
        )
        return {row[0]: row[1] for row in result.all() if row[0] is not None}

    async def planned_before(
        self, user_id: uuid.UUID, month: date
    ) -> dict[uuid.UUID, Decimal]:
        result = await self._session.execute(
            select(
                Budget.category_id,
                func.coalesce(func.sum(Budget.planned), Decimal(0)),
            )
            .where(
                Budget.user_id == user_id,
                Budget.month < month,
            )
            .group_by(Budget.category_id)
        )
        return {row[0]: row[1] for row in result.all()}

    async def spent_before(
        self, user_id: uuid.UUID, before: datetime
    ) -> dict[uuid.UUID, Decimal]:
        result = await self._session.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_rub), Decimal(0)),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.EXPENSE,
                Transaction.date < before,
            )
            .group_by(Transaction.category_id)
        )
        return {row[0]: row[1] for row in result.all() if row[0] is not None}
