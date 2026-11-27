"""Импорт не переспрашивает базу об одном и том же на каждой строке.

До памяти на время запроса (``import_/caching.py``) выписка в N строк
делала N запросов за счётом, N за категорией, N за её родителем и N за
получателем — на выписке в 2000 строк это тысячи одинаковых SELECT
внутри одной открытой транзакции.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.domains.categories.models import Category
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.import_.caching import (
    CachedAccountRepository,
    CachedCategoryRepository,
    CachedCurrencyService,
    CachedPayeeService,
)
from app.domains.import_.repository import SqlImportRepository
from app.domains.import_.service import ImportService
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.schemas import TransactionCreate
from app.domains.transactions.service import TransactionService

ROWS = 40


class _NoProvider:
    """Курсы никто не тянет: счёт рублёвый."""

    async def fetch_rates(self, base: str) -> dict[str, Decimal]:
        raise AssertionError("провайдер курсов не должен понадобиться")


def _service(session: AsyncSession) -> ImportService:
    """Тот же набор, что собирает get_import_service на маршруте."""
    currencies = CachedCurrencyService(
        SqlCurrencyRepository(session), _NoProvider()
    )
    transactions = TransactionService(
        SqlTransactionRepository(session),
        CachedAccountRepository(session),
        CachedCategoryRepository(session),
        currencies,
        CachedPayeeService(SqlPayeeRepository(session)),
    )
    return ImportService(SqlImportRepository(session), transactions)


def _selects_from(statements: list[str], table: str) -> int:
    return sum(
        1
        for text in statements
        if text.lstrip().upper().startswith("SELECT")
        and f"from {table}" in text.lower()
    )


async def test_import_asks_the_database_once_per_thing(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    user_id = ledger["user"]
    parent = Category(user_id=user_id, name="Еда", kind=CategoryKind.EXPENSE)
    db_session.add(parent)
    await db_session.flush()
    child = Category(
        user_id=user_id,
        parent_id=parent.id,
        name="Продукты",
        kind=CategoryKind.EXPENSE,
    )
    db_session.add(child)
    await db_session.flush()

    items = [
        TransactionCreate(
            account_id=ledger["rub"],
            kind=TransactionKind.EXPENSE,
            amount=Decimal("431.00"),
            date=datetime(2026, 11, 20, 12, 0, tzinfo=UTC),
            category_id=child.id,
            payee="Пятёрочка",
            comment=f"строка {i}",
        )
        for i in range(ROWS)
    ]

    seen: list[str] = []

    def _record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", _record)
    try:
        created = await _service(db_session).import_transactions(
            user_id, items
        )
    finally:
        event.remove(Engine, "before_cursor_execute", _record)

    assert created == ROWS

    # Счёт у выписки один, категория одна (плюс её родитель),
    # получатель один — по одному запросу на каждого, а не по ROWS.
    # Замер на этих же 40 строках: было accounts=40, categories=80,
    # payees=40, всего 202 запроса; стало 1, 2, 1 и всего 46.
    assert _selects_from(seen, "accounts") <= 2
    assert _selects_from(seen, "categories") <= 3
    assert _selects_from(seen, "payees") <= 2

    rows = await db_session.execute(
        Transaction.__table__.select().where(Transaction.user_id == user_id)
    )
    assert len(list(rows)) == ROWS
