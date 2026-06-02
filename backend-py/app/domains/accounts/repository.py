"""Доступ к БД для домена accounts."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts.models import Account
from app.domains.currencies.models import Currency

__all__ = ["AccountRepository", "SqlAccountRepository"]


class AccountRepository(Protocol):
    async def list_active(self, user_id: uuid.UUID) -> list[Account]: ...

    async def get(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Account | None: ...

    async def get_active_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> Account | None: ...

    async def currency_exists(self, code: str) -> bool: ...

    async def add(self, account: Account) -> Account: ...


class SqlAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, user_id: uuid.UUID) -> list[Account]:
        result = await self._session.execute(
            select(Account)
            .where(
                Account.user_id == user_id,
                Account.is_archived.is_(False),
            )
            .order_by(Account.sort_order, Account.name)
        )
        return list(result.scalars().all())

    async def get(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Account | None:
        result = await self._session.execute(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> Account | None:
        result = await self._session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.name == name,
                Account.is_archived.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def currency_exists(self, code: str) -> bool:
        result = await self._session.execute(
            select(Currency.code).where(Currency.code == code)
        )
        return result.scalar_one_or_none() is not None

    async def add(self, account: Account) -> Account:
        self._session.add(account)
        await self._session.flush()
        return account
