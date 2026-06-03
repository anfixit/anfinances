"""Доступ к БД для домена import_.

Пишет чужие модели (восстановление бэкапа) и проверяет «пустоту»
финансовых данных. Без бизнес-логики и без commit (ADR-013).
"""

import uuid
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts.models import Account
from app.domains.auth.models import User
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.currencies.models import Currency, UserCurrency
from app.domains.recurring.models import RecurringExpense
from app.domains.transactions.models import Transaction, Transfer

__all__ = ["ImportRepository", "SqlImportRepository"]

# Наличие любой из этих сущностей = аккаунт «не пустой».
# Категории и валюты юзера — конфиг (есть дефолты), не считаются.
_DATA_MODELS = (Account, Transaction, Transfer, Budget, RecurringExpense)


class ImportRepository(Protocol):
    async def has_user_data(self, user_id: uuid.UUID) -> bool: ...

    async def clear_config(self, user_id: uuid.UUID) -> None: ...

    async def existing_currency_codes(self) -> set[str]: ...

    async def add_all(self, objects: list[object]) -> None: ...

    async def get_user(self, user_id: uuid.UUID) -> User | None: ...


class SqlImportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_user_data(self, user_id: uuid.UUID) -> bool:
        for model in _DATA_MODELS:
            result = await self._session.execute(
                select(model.id).where(model.user_id == user_id).limit(1)
            )
            if result.first() is not None:
                return True
        return False

    async def clear_config(self, user_id: uuid.UUID) -> None:
        # Безопасно: has_user_data уже гарантировал отсутствие
        # транзакций/бюджетов/плана, ссылающихся на категории.
        await self._session.execute(
            delete(UserCurrency).where(UserCurrency.user_id == user_id)
        )
        await self._session.execute(
            delete(Category).where(Category.user_id == user_id)
        )
        await self._session.flush()

    async def existing_currency_codes(self) -> set[str]:
        result = await self._session.execute(select(Currency.code))
        return {row[0] for row in result.all()}

    async def add_all(self, objects: list[object]) -> None:
        self._session.add_all(objects)
        await self._session.flush()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)
