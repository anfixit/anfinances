"""Доступ к БД для домена users.

Домен обслуживает профиль текущего юзера и его набор валют,
поэтому читает чужие модели (``User`` из auth, ``UserCurrency`` и
``Currency`` из currencies) — как transactions читает accounts и
categories. Без бизнес-логики и без commit (ADR-013).
"""

import uuid
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.currencies.models import Currency, UserCurrency

__all__ = ["UserRepository", "SqlUserRepository"]


class UserRepository(Protocol):
    async def get_user(self, user_id: uuid.UUID) -> User | None: ...

    async def currency_exists(self, code: str) -> bool: ...

    async def list_user_currencies(
        self, user_id: uuid.UUID
    ) -> list[UserCurrency]: ...

    async def replace_user_currencies(
        self,
        user_id: uuid.UUID,
        items: list[UserCurrency],
    ) -> list[UserCurrency]: ...


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def currency_exists(self, code: str) -> bool:
        result = await self._session.execute(
            select(Currency.code).where(Currency.code == code)
        )
        return result.first() is not None

    async def list_user_currencies(
        self, user_id: uuid.UUID
    ) -> list[UserCurrency]:
        result = await self._session.execute(
            select(UserCurrency)
            .where(UserCurrency.user_id == user_id)
            .order_by(UserCurrency.sort_order, UserCurrency.currency_code)
        )
        return list(result.scalars().all())

    async def replace_user_currencies(
        self,
        user_id: uuid.UUID,
        items: list[UserCurrency],
    ) -> list[UserCurrency]:
        # PUT — полная замена набора: чистим старое, кладём новое.
        await self._session.execute(
            delete(UserCurrency).where(UserCurrency.user_id == user_id)
        )
        for item in items:
            self._session.add(item)
        await self._session.flush()
        return items
