"""Память на время одного импорта.

Импорт зовёт ``create_transaction`` на каждую строку выписки, и та
каждый раз спрашивает у базы одно и то же: счёт у выписки один,
категорий в ней десяток, получатель повторяется из строки в строку, а
курс валюты за время запроса не меняется. На выписке в 2000 строк это
тысячи одинаковых запросов внутри одной открытой транзакции — на
сервере с гигабайтом памяти лишнее.

Подменяем только на маршруте импорта (``get_import_service``): эти
объекты живут ровно один запрос, устареть им негде, а остальные
маршруты работают с обычными репозиториями и сервисами. Бизнес-логика
не меняется: те же проверки, тот же знак суммы, тот же курс.

Промах и попадание различаем по наличию ключа, а не по ``None``:
«счёта нет» — тоже ответ, и переспрашивать его незачем.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts.models import Account
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import RatesProvider
from app.domains.currencies.repository import CurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.payees.models import Payee
from app.domains.payees.repository import PayeeRepository
from app.domains.payees.service import PayeeService, payee_key

__all__ = [
    "CachedAccountRepository",
    "CachedCategoryRepository",
    "CachedCurrencyService",
    "CachedPayeeService",
]

_Key = tuple[uuid.UUID, uuid.UUID]


class CachedAccountRepository(SqlAccountRepository):
    """Счёт выписки спрашиваем у базы один раз, а не на каждой строке."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._seen: dict[_Key, Account | None] = {}

    async def get(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Account | None:
        key = (account_id, user_id)
        if key not in self._seen:
            self._seen[key] = await super().get(account_id, user_id)
        return self._seen[key]


class CachedCategoryRepository(SqlCategoryRepository):
    """Категории в выписке повторяются — и сами, и их родители."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._seen: dict[_Key, Category | None] = {}

    async def get(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> Category | None:
        key = (category_id, user_id)
        if key not in self._seen:
            self._seen[key] = await super().get(category_id, user_id)
        return self._seen[key]


class CachedCurrencyService(CurrencyService):
    """Курс к рублю за один запрос не меняется."""

    def __init__(
        self, repo: CurrencyRepository, provider: RatesProvider
    ) -> None:
        super().__init__(repo, provider)
        self._rates: dict[str, Decimal] = {}

    async def rate_to_rub(self, code: str) -> Decimal:
        if code not in self._rates:
            # Отсутствие курса — исключение; его не запоминаем,
            # запомнить нечего.
            self._rates[code] = await super().rate_to_rub(code)
        return self._rates[code]


class CachedPayeeService(PayeeService):
    """Один получатель на всю выписку — один поиск и одна вставка.

    Ключ тот же, по которому получатели считаются одним (``payee_key``):
    «Пятёрочка» и «пятёрочка» в одной выписке — один и тот же магазин.
    """

    def __init__(self, repo: PayeeRepository) -> None:
        super().__init__(repo)
        self._by_key: dict[str, Payee] = {}

    async def ensure(self, user_id: uuid.UUID, name: str) -> Payee:
        key = payee_key(name)
        cached = self._by_key.get(key)
        if cached is not None:
            return cached
        payee = await super().ensure(user_id, name)
        self._by_key[key] = payee
        return payee
