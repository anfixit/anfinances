"""Доступ к БД для домена credits."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.credits.models import Credit, CreditPayment
from app.domains.currencies.models import Currency
from app.domains.transactions.models import Transaction

__all__ = ["CreditRepository", "SqlCreditRepository"]


class CreditRepository(Protocol):
    async def list_active(self, user_id: uuid.UUID) -> list[Credit]: ...

    async def get(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> Credit | None: ...

    async def get_active_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> Credit | None: ...

    async def currency_exists(self, code: str) -> bool: ...

    async def has_payments(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool: ...

    async def list_payments(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CreditPayment]: ...

    async def add(self, credit: Credit) -> Credit: ...

    async def add_payment(self, payment: CreditPayment) -> CreditPayment: ...

    async def get_payment(
        self, payment_id: uuid.UUID, user_id: uuid.UUID
    ) -> CreditPayment | None: ...

    async def delete_payment(self, payment: CreditPayment) -> None: ...

    async def delete_transaction(self, tx_id: uuid.UUID) -> None: ...


class SqlCreditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, user_id: uuid.UUID) -> list[Credit]:
        result = await self._session.execute(
            select(Credit)
            .where(
                Credit.user_id == user_id,
                Credit.is_archived.is_(False),
            )
            .order_by(Credit.name)
        )
        return list(result.scalars().all())

    async def get(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> Credit | None:
        result = await self._session.execute(
            select(Credit).where(
                Credit.id == credit_id,
                Credit.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> Credit | None:
        result = await self._session.execute(
            select(Credit).where(
                Credit.user_id == user_id,
                Credit.name == name,
                Credit.is_archived.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def currency_exists(self, code: str) -> bool:
        result = await self._session.execute(
            select(Currency.code).where(Currency.code == code)
        )
        return result.scalar_one_or_none() is not None

    async def has_payments(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        result = await self._session.execute(
            select(CreditPayment.id)
            .where(
                CreditPayment.credit_id == credit_id,
                CreditPayment.user_id == user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_payments(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CreditPayment]:
        result = await self._session.execute(
            select(CreditPayment)
            .where(
                CreditPayment.credit_id == credit_id,
                CreditPayment.user_id == user_id,
            )
            .order_by(CreditPayment.date.desc(), CreditPayment.id.desc())
        )
        return list(result.scalars().all())

    async def add(self, credit: Credit) -> Credit:
        self._session.add(credit)
        await self._session.flush()
        return credit

    async def add_payment(self, payment: CreditPayment) -> CreditPayment:
        self._session.add(payment)
        await self._session.flush()
        return payment

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

    async def delete_payment(self, payment: CreditPayment) -> None:
        await self._session.delete(payment)

    async def delete_transaction(self, tx_id: uuid.UUID) -> None:
        """Снести списание, созданное вместе с платежом."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.id == tx_id)
        )
        tx = result.scalar_one_or_none()
        if tx is not None:
            await self._session.delete(tx)
