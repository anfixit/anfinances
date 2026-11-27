"""Доступ к БД для домена import_.

Пишет чужие модели (восстановление бэкапа) и проверяет «пустоту»
финансовых данных. Без бизнес-логики и без commit (ADR-013).
"""

import uuid
from collections import defaultdict
from typing import Protocol, cast

from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Base
from app.domains.accounts.models import Account
from app.domains.auth.models import User
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.credits.models import Credit, CreditPayment
from app.domains.currencies.models import Currency, UserCurrency
from app.domains.goals.models import CategoryGoal
from app.domains.payees.models import Payee, PayeeCandidate
from app.domains.reconciliation.models import Reconciliation
from app.domains.recurring.models import RecurringExpense
from app.domains.transactions.models import Transaction, Transfer

__all__ = ["ImportRepository", "SqlImportRepository"]

# Наличие любой из этих сущностей = аккаунт «не пустой».
# Категории и валюты юзера — конфиг (есть дефолты), не считаются.
# Цели — считаются: clear_config удаляет категории, а цели держатся
# на них каскадом и молча исчезли бы вместе с ними.
_DATA_MODELS = (
    Account,
    Transaction,
    Transfer,
    Budget,
    RecurringExpense,
    Credit,
    CreditPayment,
    Payee,
    CategoryGoal,
    Reconciliation,
)


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
        # Отклонённые имена из интерфейса не удаляются, и в «пустом»
        # аккаунте они могли остаться: бэкап принесёт свои, терять
        # нечего, а старые упёрлись бы в уникальный индекс.
        await self._session.execute(
            delete(PayeeCandidate).where(PayeeCandidate.user_id == user_id)
        )
        await self._session.execute(
            delete(Category).where(Category.user_id == user_id)
        )
        await self._session.flush()

    async def existing_currency_codes(self) -> set[str]:
        result = await self._session.execute(select(Currency.code))
        return {row[0] for row in result.all()}

    async def add_all(self, objects: list[object]) -> None:
        """Вставить строки бэкапа в порядке внешних ключей.

        В моделях нет ``relationship()``, и unit of work не знает, какая
        таблица от какой зависит: вставляет их в порядке имён классов.
        На PostgreSQL бюджет уходил раньше категории, операция — раньше
        своего перевода, и восстановление падало на внешнем ключе.
        SQLite в тестах ключи не проверяет, поэтому это не ловилось.
        Здесь — по таблицам в порядке ``sorted_tables``, с flush после
        каждой; категории ссылаются сами на себя, их — от корней.
        """
        order = {t.name: i for i, t in enumerate(Base.metadata.sorted_tables)}
        by_table: dict[str, list[Base]] = defaultdict(list)
        for obj in objects:
            row = cast(Base, obj)
            by_table[cast(Table, row.__table__).name].append(row)
        for name in sorted(by_table, key=order.__getitem__):
            for layer in _parents_first(by_table[name]):
                self._session.add_all(layer)
                await self._session.flush()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)


def _parents_first(rows: list[Base]) -> list[list[Base]]:
    """Разбить строки на слои: сначала без родителя в этой же пачке.

    Для таблиц без ``parent_id`` — один слой как есть.
    """
    if not rows or not hasattr(rows[0], "parent_id"):
        return [rows]
    ids = {getattr(r, "id", None) for r in rows}
    placed: set[object] = set()
    layers: list[list[Base]] = []
    left = rows
    while left:
        layer = [
            r
            for r in left
            if getattr(r, "parent_id", None) not in ids
            or getattr(r, "parent_id", None) in placed
        ]
        if not layer:
            # Цикл в дереве — пусть база скажет, где именно.
            layer = left
        layers.append(layer)
        placed |= {getattr(r, "id", None) for r in layer}
        left = [r for r in left if r not in layer]
    return layers
