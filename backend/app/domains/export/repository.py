"""Доступ к БД для домена export.

Тонкий read-only слой с bulk-выборками: существующие доменные
репозитории отдают только активные/постраничные данные, а для
выгрузки и бэкапа нужны все строки юзера (включая архивные).
Читает чужие модели — как transactions читает accounts/categories.
"""

import uuid
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts.models import Account
from app.domains.auth.models import User
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.currencies.models import UserCurrency
from app.domains.recurring.models import RecurringExpense
from app.domains.transactions.models import Transaction, Transfer

__all__ = ["ExportRepository", "SqlExportRepository"]


class ExportRepository(Protocol):
    async def get_user(self, user_id: uuid.UUID) -> User | None: ...

    async def list_user_currencies(
        self, user_id: uuid.UUID
    ) -> list[UserCurrency]: ...

    async def list_accounts(self, user_id: uuid.UUID) -> list[Account]: ...

    async def list_categories(self, user_id: uuid.UUID) -> list[Category]: ...

    async def list_transfers(self, user_id: uuid.UUID) -> list[Transfer]: ...

    async def list_transactions(
        self,
        user_id: uuid.UUID,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[Transaction]: ...

    async def list_budgets(self, user_id: uuid.UUID) -> list[Budget]: ...

    async def list_recurring(
        self, user_id: uuid.UUID
    ) -> list[RecurringExpense]: ...


class SqlExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list_user_currencies(
        self, user_id: uuid.UUID
    ) -> list[UserCurrency]:
        result = await self._session.execute(
            select(UserCurrency)
            .where(UserCurrency.user_id == user_id)
            .order_by(UserCurrency.sort_order, UserCurrency.currency_code)
        )
        return list(result.scalars().all())

    async def list_accounts(self, user_id: uuid.UUID) -> list[Account]:
        result = await self._session.execute(
            select(Account)
            .where(Account.user_id == user_id)
            .order_by(Account.sort_order, Account.name)
        )
        return list(result.scalars().all())

    async def list_categories(self, user_id: uuid.UUID) -> list[Category]:
        result = await self._session.execute(
            select(Category)
            .where(Category.user_id == user_id)
            .order_by(Category.sort_order, Category.name)
        )
        return list(result.scalars().all())

    async def list_transfers(self, user_id: uuid.UUID) -> list[Transfer]:
        result = await self._session.execute(
            select(Transfer).where(Transfer.user_id == user_id)
        )
        return list(result.scalars().all())

    async def list_transactions(
        self,
        user_id: uuid.UUID,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.user_id == user_id)
        if date_from is not None:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.date < date_to)
        stmt = stmt.order_by(Transaction.date, Transaction.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_budgets(self, user_id: uuid.UUID) -> list[Budget]:
        result = await self._session.execute(
            select(Budget)
            .where(Budget.user_id == user_id)
            .order_by(Budget.month, Budget.created_at)
        )
        return list(result.scalars().all())

    async def list_recurring(
        self, user_id: uuid.UUID
    ) -> list[RecurringExpense]:
        result = await self._session.execute(
            select(RecurringExpense)
            .where(RecurringExpense.user_id == user_id)
            .order_by(RecurringExpense.name)
        )
        return list(result.scalars().all())
