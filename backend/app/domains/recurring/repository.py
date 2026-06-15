"""Доступ к БД для домена recurring.

Содержит только запросы, без бизнес-логики и без commit —
транзакцией управляет роут (ADR-013). Удаление — архивирование
(soft-delete), поэтому метода delete нет: сервис ставит
``is_archived = True`` на загруженной записи.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequiredKind, TransactionKind
from app.domains.recurring.models import RecurringExpense
from app.domains.transactions.models import Transaction

__all__ = ["RecurringRepository", "SqlRecurringRepository"]


class RecurringRepository(Protocol):
    async def list_active(
        self, user_id: uuid.UUID
    ) -> list[RecurringExpense]: ...

    async def get(
        self, recurring_id: uuid.UUID, user_id: uuid.UUID
    ) -> RecurringExpense | None: ...

    async def add(self, item: RecurringExpense) -> RecurringExpense: ...

    async def required_spend_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> dict[uuid.UUID, Decimal]: ...


class SqlRecurringRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, user_id: uuid.UUID) -> list[RecurringExpense]:
        result = await self._session.execute(
            select(RecurringExpense)
            .where(
                RecurringExpense.user_id == user_id,
                RecurringExpense.is_archived.is_(False),
            )
            .order_by(RecurringExpense.name)
        )
        return list(result.scalars().all())

    async def get(
        self, recurring_id: uuid.UUID, user_id: uuid.UUID
    ) -> RecurringExpense | None:
        result = await self._session.execute(
            select(RecurringExpense).where(
                RecurringExpense.id == recurring_id,
                RecurringExpense.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, item: RecurringExpense) -> RecurringExpense:
        self._session.add(item)
        await self._session.flush()
        return item

    async def required_spend_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> dict[uuid.UUID, Decimal]:
        # Обязательные расходы за окно, сгруппированные по категории.
        # amount_rub хранится со знаком (расход < 0).
        result = await self._session.execute(
            select(
                Transaction.category_id,
                func.coalesce(func.sum(Transaction.amount_rub), Decimal(0)),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.EXPENSE,
                Transaction.required == RequiredKind.REQUIRED,
                Transaction.date >= date_from,
                Transaction.date < date_to,
            )
            .group_by(Transaction.category_id)
        )
        return {row[0]: row[1] for row in result.all() if row[0] is not None}
