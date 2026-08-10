"""Каждый тип операции должен сохраняться в БД.

Регрессия: миграция кредитов добавила в тип transaction_kind метку
строчными буквами, тогда как SQLAlchemy отправляет имя члена
перечисления. На PostgreSQL вставка кредитного платежа падала с
"invalid input value for enum transaction_kind: CREDIT_PAYMENT",
а на SQLite проходила — поэтому тесты этого не видели.

Тест осмысленно ловит регрессию только на PostgreSQL (CI поднимает
его через TEST_DATABASE_URL), но и на SQLite не мешает.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.enums import TransactionKind
from app.domains.transactions.models import Transaction


@pytest.mark.parametrize("kind", list(TransactionKind))
async def test_every_kind_is_storable(
    db_session: Any,
    ledger: dict[str, uuid.UUID],
    kind: TransactionKind,
) -> None:
    # Знак подбираем под соглашение: расход и кредитный платёж
    # отрицательны, доход положителен, нога перевода — любая.
    negative = kind in {
        TransactionKind.EXPENSE,
        TransactionKind.CREDIT_PAYMENT,
    }
    amount = Decimal("-100") if negative else Decimal("100")

    db_session.add(
        Transaction(
            user_id=ledger["user"],
            account_id=ledger["rub"],
            kind=kind,
            amount=amount,
            currency_code="RUB",
            amount_rub=amount,
            exchange_rate=Decimal("1"),
            date=datetime.now(UTC),
        )
    )
    await db_session.flush()
