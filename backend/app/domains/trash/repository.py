"""Доступ к БД для корзины.

Корзина читает чужие модели — операции, переводы, платежи, кредиты —
как export и users: ей нужны строки целиком, а доменные репозитории
отдают их под свои задачи.
"""

import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Base
from app.domains.accounts.models import Account
from app.domains.categories.models import Category
from app.domains.credits.models import Credit, CreditPayment
from app.domains.payees.models import Payee
from app.domains.transactions.models import Transaction, Transfer
from app.domains.trash.models import DeletedRecord

__all__ = ["SqlTrashRepository", "TrashRepository"]


class TrashRepository(Protocol):
    async def add(self, record: DeletedRecord) -> DeletedRecord: ...

    async def list_waiting(
        self, user_id: uuid.UUID, limit: int
    ) -> list[DeletedRecord]: ...

    async def get(
        self, record_id: uuid.UUID, user_id: uuid.UUID
    ) -> DeletedRecord | None: ...

    async def get_transaction(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None: ...

    async def get_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Transfer | None, list[Transaction]]: ...

    async def get_payment(
        self, payment_id: uuid.UUID, user_id: uuid.UUID
    ) -> CreditPayment | None: ...

    async def get_credit(
        self,
        credit_id: uuid.UUID,
        user_id: uuid.UUID,
        for_update: bool = False,
    ) -> Credit | None: ...

    async def exists(self, model: type[Base], row_id: Any) -> bool: ...

    async def owns(
        self, model: type[Base], row_id: Any, user_id: uuid.UUID
    ) -> bool: ...

    async def insert(self, row: Base) -> None: ...


class SqlTrashRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: DeletedRecord) -> DeletedRecord:
        self._session.add(record)
        await self._session.flush()
        return record

    async def list_waiting(
        self, user_id: uuid.UUID, limit: int
    ) -> list[DeletedRecord]:
        result = await self._session.execute(
            select(DeletedRecord)
            .where(
                DeletedRecord.user_id == user_id,
                DeletedRecord.restored_at.is_(None),
            )
            .order_by(DeletedRecord.deleted_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get(
        self, record_id: uuid.UUID, user_id: uuid.UUID
    ) -> DeletedRecord | None:
        result = await self._session.execute(
            select(DeletedRecord).where(
                DeletedRecord.id == record_id,
                DeletedRecord.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_transaction(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(
                Transaction.id == tx_id, Transaction.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Transfer | None, list[Transaction]]:
        result = await self._session.execute(
            select(Transfer).where(
                Transfer.id == transfer_id, Transfer.user_id == user_id
            )
        )
        transfer = result.scalar_one_or_none()
        if transfer is None:
            return None, []
        legs = await self._session.execute(
            select(Transaction)
            .where(Transaction.transfer_id == transfer_id)
            .order_by(Transaction.amount)
        )
        return transfer, list(legs.scalars().all())

    async def get_payment(
        self, payment_id: uuid.UUID, user_id: uuid.UUID
    ) -> CreditPayment | None:
        result = await self._session.execute(
            select(CreditPayment).where(
                CreditPayment.id == payment_id,
                CreditPayment.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_credit(
        self,
        credit_id: uuid.UUID,
        user_id: uuid.UUID,
        for_update: bool = False,
    ) -> Credit | None:
        query = select(Credit).where(
            Credit.id == credit_id, Credit.user_id == user_id
        )
        if for_update:
            # Возврат платежа меняет долг — как и сам платёж, под
            # блокировкой и со свежим остатком.
            query = query.with_for_update().execution_options(
                populate_existing=True
            )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def exists(self, model: type[Base], row_id: Any) -> bool:
        return await self._session.get(model, row_id) is not None

    async def owns(
        self, model: type[Base], row_id: Any, user_id: uuid.UUID
    ) -> bool:
        row = await self._session.get(model, row_id)
        return row is not None and getattr(row, "user_id", None) == user_id

    async def insert(self, row: Base) -> None:
        # По одной строке: нога перевода ссылается на узел, платёж —
        # на своё списание, и порядок вставки должен это соблюдать.
        self._session.add(row)
        await self._session.flush()


# Модели, на которые ссылаются строки корзины: при возврате проверяем,
# что они ещё есть у этого пользователя.
REFERENCED = {
    "account_id": Account,
    "payment_account_id": Account,
    "category_id": Category,
    "interest_category_id": Category,
    "fee_category_id": Category,
    "payee_id": Payee,
}
