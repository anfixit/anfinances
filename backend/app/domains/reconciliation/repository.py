"""Доступ к БД для домена reconciliation."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.reconciliation.models import Reconciliation
from app.domains.transactions.models import Transaction

__all__ = ["ReconciliationRepository", "SqlReconciliationRepository"]


class ReconciliationRepository(Protocol):
    async def balance_at(
        self, account_id: uuid.UUID, user_id: uuid.UUID, moment: datetime
    ) -> Decimal: ...

    async def unreconciled_count(
        self, account_id: uuid.UUID, user_id: uuid.UUID, moment: datetime
    ) -> int: ...

    async def mark_reconciled(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        moment: datetime,
        stamp: datetime,
    ) -> int: ...

    async def add(self, row: Reconciliation) -> Reconciliation: ...

    async def history(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Reconciliation]: ...

    async def latest_per_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]: ...


class SqlReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def balance_at(
        self, account_id: uuid.UUID, user_id: uuid.UUID, moment: datetime
    ) -> Decimal:
        """Сумма операций по счёту до момента включительно.

        Начальный остаток сюда не входит: его добавляет сервис, у
        которого есть сам счёт.
        """
        result = await self._session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account_id,
                Transaction.user_id == user_id,
                Transaction.date <= moment,
            )
        )
        total: Decimal = result.scalar_one()
        return total

    async def unreconciled_count(
        self, account_id: uuid.UUID, user_id: uuid.UUID, moment: datetime
    ) -> int:
        result = await self._session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.account_id == account_id,
                Transaction.user_id == user_id,
                Transaction.date <= moment,
                Transaction.reconciled_at.is_(None),
            )
        )
        count: int = result.scalar_one()
        return count

    async def mark_reconciled(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        moment: datetime,
        stamp: datetime,
    ) -> int:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.user_id == user_id,
                Transaction.date <= moment,
                Transaction.reconciled_at.is_(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.reconciled_at = stamp
        await self._session.flush()
        return len(rows)

    async def add(self, row: Reconciliation) -> Reconciliation:
        self._session.add(row)
        await self._session.flush()
        return row

    async def history(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Reconciliation]:
        result = await self._session.execute(
            select(Reconciliation)
            .where(
                Reconciliation.account_id == account_id,
                Reconciliation.user_id == user_id,
            )
            .order_by(Reconciliation.date.desc())
        )
        return list(result.scalars().all())

    async def latest_per_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]:
        """Дата последней сверки по каждому счёту.

        Нужна списку счетов: «сверен до 21.08» рядом с остатком —
        единственное место, где привычка сверять вообще заводится.
        """
        result = await self._session.execute(
            select(Reconciliation.account_id, func.max(Reconciliation.date))
            .where(Reconciliation.user_id == user_id)
            .group_by(Reconciliation.account_id)
        )
        return {row[0]: row[1] for row in result.all()}
