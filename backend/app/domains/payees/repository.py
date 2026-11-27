"""Доступ к БД для домена payees."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.payees.keys import payee_key
from app.domains.payees.models import Payee, PayeeCandidate
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

    async def get_candidate(
        self, user_id: uuid.UUID, name_key: str
    ) -> PayeeCandidate | None: ...

    async def add_candidate(
        self, candidate: PayeeCandidate
    ) -> PayeeCandidate: ...

    async def list_candidates(
        self, user_id: uuid.UUID, status: str
    ) -> list[PayeeCandidate]: ...

    async def get_candidate_by_id(
        self, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> PayeeCandidate | None: ...

    async def delete_candidate(self, candidate: PayeeCandidate) -> None: ...

    async def reassign(
        self, from_payee_id: uuid.UUID, to_payee_id: uuid.UUID
    ) -> int: ...

    async def reassign_orphans(
        self, user_id: uuid.UUID, name_key: str, payee_id: uuid.UUID
    ) -> tuple[int, uuid.UUID | None]: ...

    async def candidate_totals(
        self, user_id: uuid.UUID, name_keys: list[str]
    ) -> dict[str, Decimal]: ...

    async def spending_by_payee(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID, str, Decimal, int]]: ...

    async def unsorted_spending(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[int, Decimal]: ...


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

    async def get_candidate(
        self, user_id: uuid.UUID, name_key: str
    ) -> PayeeCandidate | None:
        result = await self._session.execute(
            select(PayeeCandidate).where(
                PayeeCandidate.user_id == user_id,
                PayeeCandidate.name_key == name_key,
            )
        )
        return result.scalar_one_or_none()

    async def add_candidate(self, candidate: PayeeCandidate) -> PayeeCandidate:
        self._session.add(candidate)
        await self._session.flush()
        return candidate

    async def list_candidates(
        self, user_id: uuid.UUID, status: str
    ) -> list[PayeeCandidate]:
        result = await self._session.execute(
            select(PayeeCandidate)
            .where(
                PayeeCandidate.user_id == user_id,
                PayeeCandidate.status == status,
            )
            .order_by(PayeeCandidate.name_key)
        )
        return list(result.scalars().all())

    async def get_candidate_by_id(
        self, candidate_id: uuid.UUID, user_id: uuid.UUID
    ) -> PayeeCandidate | None:
        result = await self._session.execute(
            select(PayeeCandidate).where(
                PayeeCandidate.id == candidate_id,
                PayeeCandidate.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_candidate(self, candidate: PayeeCandidate) -> None:
        await self._session.delete(candidate)

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

    async def reassign_orphans(
        self, user_id: uuid.UUID, name_key: str, payee_id: uuid.UUID
    ) -> tuple[int, uuid.UUID | None]:
        """Перевесить операции без получателя, чьё имя сворачивается в ключ.

        Возвращает сколько перевешено и категорию самой свежей из них:
        ею засевается память получателя. Имя в снимке сворачиваем в
        питоне, а не в SQL: lower() в SQLite кириллицу не трогает.
        """
        result = await self._session.execute(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.payee_id.is_(None),
                Transaction.payee_name_snapshot.is_not(None),
                Transaction.payee_name_snapshot != "",
            )
            .order_by(Transaction.date.desc())
        )
        rows = [
            tx
            for tx in result.scalars().all()
            if tx.payee_name_snapshot is not None
            and payee_key(tx.payee_name_snapshot) == name_key
        ]
        for tx in rows:
            tx.payee_id = payee_id
        await self._session.flush()
        return len(rows), rows[0].category_id if rows else None

    async def candidate_totals(
        self, user_id: uuid.UUID, name_keys: list[str]
    ) -> dict[str, Decimal]:
        """Сколько потрачено по осиротевшим операциям каждого имени.

        Один проход по всем операциям без получателя: свёртка имени в
        питоне, поэтому SQL-группировкой не обойтись. Считаются расходы
        и возвраты, как в отчёте по получателям; имена без таких
        операций в ответе не появляются.
        """
        wanted = set(name_keys)
        result = await self._session.execute(
            select(
                Transaction.payee_name_snapshot, Transaction.amount_rub
            ).where(
                Transaction.user_id == user_id,
                Transaction.payee_id.is_(None),
                Transaction.payee_name_snapshot.is_not(None),
                Transaction.payee_name_snapshot != "",
                Transaction.kind.in_(
                    (TransactionKind.EXPENSE, TransactionKind.REFUND)
                ),
            )
        )
        totals: dict[str, Decimal] = {}
        for snapshot, amount_rub in result.all():
            key = payee_key(snapshot)
            if key in wanted:
                totals[key] = totals.get(key, Decimal(0)) - amount_rub
        return totals

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
                Transaction.kind.in_(
                    (TransactionKind.EXPENSE, TransactionKind.REFUND)
                ),
                Transaction.date >= date_from,
                Transaction.date < date_to,
            )
            .group_by(Payee.id, Payee.name)
            .order_by(func.sum(Transaction.amount_rub))
        )
        return [
            (row[0], row[1], -(row[2] or Decimal(0)), row[3])
            for row in result.all()
        ]

    async def unsorted_spending(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> tuple[int, Decimal]:
        """Сколько имён ждут разбора и сколько по ним потрачено за период.

        Тот же период и те же виды операций, что у spending_by_payee.
        Имён считаем по свёрнутому ключу, а не по операциям, поэтому
        свёртка в питоне, как в candidate_totals.
        """
        result = await self._session.execute(
            select(
                Transaction.payee_name_snapshot, Transaction.amount_rub
            ).where(
                Transaction.user_id == user_id,
                Transaction.payee_id.is_(None),
                Transaction.payee_name_snapshot.is_not(None),
                Transaction.payee_name_snapshot != "",
                Transaction.kind.in_(
                    (TransactionKind.EXPENSE, TransactionKind.REFUND)
                ),
                Transaction.date >= date_from,
                Transaction.date < date_to,
            )
        )
        keys: set[str] = set()
        total = Decimal(0)
        for snapshot, amount_rub in result.all():
            keys.add(payee_key(snapshot))
            total -= amount_rub
        return len(keys), total
