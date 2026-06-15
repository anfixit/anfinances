"""Доступ к БД для домена transactions."""

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.transactions.models import Transaction, Transfer

__all__ = ["TransactionRepository", "SqlTransactionRepository"]


class TransactionFilter:
    """Параметры фильтрации/пагинации списка транзакций."""

    def __init__(
        self,
        *,
        limit: int = 20,
        cursor_date: datetime | None = None,
        cursor_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        account_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        kind: TransactionKind | None = None,
    ) -> None:
        self.limit = limit
        self.cursor_date = cursor_date
        self.cursor_id = cursor_id
        self.date_from = date_from
        self.date_to = date_to
        self.account_id = account_id
        self.category_id = category_id
        self.kind = kind


class TransactionRepository(Protocol):
    async def list_page(
        self, user_id: uuid.UUID, flt: TransactionFilter
    ) -> list[Transaction]: ...

    async def get(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None: ...

    async def add(self, tx: Transaction) -> Transaction: ...

    async def delete(self, tx: Transaction) -> None: ...

    async def add_transfer(self, transfer: Transfer) -> Transfer: ...

    async def get_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transfer | None: ...

    async def list_transfer_legs(
        self, transfer_id: uuid.UUID
    ) -> list[Transaction]: ...

    async def delete_transfer(self, transfer: Transfer) -> None: ...


class SqlTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_page(
        self, user_id: uuid.UUID, flt: TransactionFilter
    ) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        if flt.date_from is not None:
            stmt = stmt.where(Transaction.date >= flt.date_from)
        if flt.date_to is not None:
            stmt = stmt.where(Transaction.date <= flt.date_to)
        if flt.account_id is not None:
            stmt = stmt.where(Transaction.account_id == flt.account_id)
        if flt.category_id is not None:
            stmt = stmt.where(Transaction.category_id == flt.category_id)
        if flt.kind is not None:
            stmt = stmt.where(Transaction.kind == flt.kind)

        # Курсор: (date, id) строго меньше предыдущей страницы.
        if flt.cursor_date is not None and flt.cursor_id is not None:
            stmt = stmt.where(
                (Transaction.date, Transaction.id)
                < (flt.cursor_date, flt.cursor_id)
            )

        stmt = stmt.order_by(
            Transaction.date.desc(), Transaction.id.desc()
        ).limit(flt.limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.id == tx_id,
                Transaction.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, tx: Transaction) -> Transaction:
        self._session.add(tx)
        await self._session.flush()
        return tx

    async def delete(self, tx: Transaction) -> None:
        await self._session.delete(tx)

    async def add_transfer(self, transfer: Transfer) -> Transfer:
        self._session.add(transfer)
        await self._session.flush()
        return transfer

    async def get_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transfer | None:
        result = await self._session.execute(
            select(Transfer).where(
                Transfer.id == transfer_id,
                Transfer.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_transfer_legs(
        self, transfer_id: uuid.UUID
    ) -> list[Transaction]:
        result = await self._session.execute(
            select(Transaction).where(Transaction.transfer_id == transfer_id)
        )
        return list(result.scalars().all())

    async def delete_transfer(self, transfer: Transfer) -> None:
        await self._session.delete(transfer)
