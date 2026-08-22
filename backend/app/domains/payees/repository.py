"""Доступ к БД для домена payees."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.payees.models import Payee
from app.domains.transactions.models import Transaction

__all__ = ["PayeeRepository", "SqlPayeeRepository"]


class PayeeRepository(Protocol):
    async def list_all(self, user_id: uuid.UUID) -> list[Payee]: ...

    async def get(
        self, payee_id: uuid.UUID, user_id: uuid.UUID
    ) -> Payee | None: ...

    async def get_by_key(
        self, user_id: uuid.UUID, name_key: str
    ) -> Payee | None: ...

    async def add(self, payee: Payee) -> Payee: ...

    async def delete(self, payee: Payee) -> None: ...

    async def reassign(
        self, from_payee_id: uuid.UUID, to_payee_id: uuid.UUID
    ) -> int: ...

    async def spending_by_payee(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID, str, Decimal, int]]: ...

    async def first_seen(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]: ...


class SqlPayeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, user_id: uuid.UUID) -> list[Payee]:
        result = await self._session.execute(
            select(Payee)
            .where(Payee.user_id == user_id)
            .order_by(Payee.name_key)
        )
        return list(result.scalars().all())

    async def get(
        self, payee_id: uuid.UUID, user_id: uuid.UUID
    ) -> Payee | None:
        result = await self._session.execute(
            select(Payee).where(
                Payee.id == payee_id,
                Payee.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, user_id: uuid.UUID, name_key: str
    ) -> Payee | None:
        result = await self._session.execute(
            select(Payee).where(
                Payee.user_id == user_id,
                Payee.name_key == name_key,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, payee: Payee) -> Payee:
        self._session.add(payee)
        await self._session.flush()
        return payee

    async def delete(self, payee: Payee) -> None:
        await self._session.delete(payee)

    async def reassign(
        self, from_payee_id: uuid.UUID, to_payee_id: uuid.UUID
    ) -> int:
        """Перевесить операции на другого получателя. Вернуть сколько."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.payee_id == from_payee_id)
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.payee_id = to_payee_id
        await self._session.flush()
        return len(rows)

    async def spending_by_payee(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID, str, Decimal, int]]:
        """Расходы по получателям за период, в рублях.

        Переводы исключены: у перемещения между своими счетами
        получателя нет, а если он проставлен по ошибке — это всё
        равно не трата.
        """
        result = await self._session.execute(
            select(
                Payee.id,
                Payee.name,
                func.sum(Transaction.amount_rub),
                func.count(Transaction.id),
            )
            .select_from(Transaction)
            .join(Payee, Payee.id == Transaction.payee_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.kind == TransactionKind.EXPENSE,
                Transaction.date >= date_from,
                Transaction.date < date_to,
            )
            .group_by(Payee.id, Payee.name)
            .order_by(func.sum(Transaction.amount_rub))
        )
        return [
            (row[0], row[1], abs(row[2] or Decimal(0)), row[3])
            for row in result.all()
        ]

    async def first_seen(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]:
        """Дата первой операции по каждому получателю.

        По ней отбираются «новые получатели»: не по дате заведения
        записи, а по первой настоящей трате — выписку заносят задним
        числом, и запись создаётся сегодня для траты трёхлетней
        давности.
        """
        result = await self._session.execute(
            select(Transaction.payee_id, func.min(Transaction.date))
            .where(
                Transaction.user_id == user_id,
                Transaction.payee_id.is_not(None),
            )
            .group_by(Transaction.payee_id)
        )
        return {row[0]: row[1] for row in result.all()}
