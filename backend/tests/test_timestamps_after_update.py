"""После UPDATE метки времени должны быть читаемы без похода в БД.

``updated_at`` проставляется выражением ``onupdate=func.now()``:
значение вычисляет база, и после UPDATE атрибут в объекте помечен
устаревшим. Любое обращение к нему тянет SELECT — а обращается к
нему pydantic при сборке ответа, синхронно и вне greenlet'а. Итог:
правка сохранена, а клиент получает 500.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TransactionKind
from app.domains.transactions.models import Transaction
from app.domains.transactions.schemas import TransactionRead


async def _make(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> Transaction:
    tx = Transaction(
        user_id=ledger["user"],
        account_id=ledger["rub"],
        kind=TransactionKind.EXPENSE,
        amount=Decimal("-100"),
        currency_code="RUB",
        amount_rub=Decimal("-100"),
        exchange_rate=Decimal("1"),
        date=datetime.now(UTC),
    )
    db_session.add(tx)
    await db_session.flush()
    return tx


async def test_read_after_insert(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _make(db_session, ledger)
    assert TransactionRead.model_validate(tx).updated_at is not None


async def test_read_after_update(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Тот самый путь, что отдавал 500 при правке операции."""
    tx = await _make(db_session, ledger)
    tx.amount = Decimal("-250")
    tx.amount_rub = Decimal("-250")
    await db_session.flush()

    read = TransactionRead.model_validate(tx)
    assert read.amount == Decimal("-250")
    assert read.updated_at is not None
