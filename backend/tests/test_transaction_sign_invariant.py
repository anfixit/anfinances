"""БД не принимает операцию с неверным знаком.

Соглашение знаков — Стратегия А: расход и кредитный платёж
отрицательны, доход положителен, знак amount_rub совпадает с amount.
Проверяем, что это держится на уровне БД, а не только в сервисе.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import TransactionKind
from app.domains.transactions.models import Transaction


def _tx(ledger: dict[str, uuid.UUID], **overrides: Any) -> Transaction:
    """Минимально валидная транзакция; поля перекрываются точечно."""
    defaults: dict[str, Any] = {
        "user_id": ledger["user"],
        "account_id": ledger["rub"],
        "kind": TransactionKind.EXPENSE,
        "amount": Decimal("-100"),
        "currency_code": "RUB",
        "amount_rub": Decimal("-100"),
        "exchange_rate": Decimal("1"),
        "date": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Transaction(**defaults)


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        (
            "расход с плюсом",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "доход с минусом",
            {
                "kind": TransactionKind.INCOME,
                "amount": Decimal("-100"),
                "amount_rub": Decimal("-100"),
            },
        ),
        (
            "кредитный платёж с плюсом",
            {
                "kind": TransactionKind.CREDIT_PAYMENT,
                "amount": Decimal("100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "знаки amount и amount_rub разошлись",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("-100"),
                "amount_rub": Decimal("100"),
            },
        ),
        (
            "нулевая сумма",
            {
                "kind": TransactionKind.EXPENSE,
                "amount": Decimal("0"),
                "amount_rub": Decimal("0"),
            },
        ),
    ],
)
async def test_bad_sign_rejected(
    db_session: Any,
    ledger: dict[str, uuid.UUID],
    label: str,
    overrides: dict[str, Any],
) -> None:
    db_session.add(_tx(ledger, **overrides))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_transfer_legs_allowed(
    db_session: Any, ledger: dict[str, uuid.UUID]
) -> None:
    """Ноги перевода знаком не ограничены — только согласованностью."""
    db_session.add(
        _tx(
            ledger,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("-500"),
            amount_rub=Decimal("-500"),
        )
    )
    db_session.add(
        _tx(
            ledger,
            kind=TransactionKind.TRANSFER,
            amount=Decimal("500"),
            amount_rub=Decimal("500"),
        )
    )
    await db_session.flush()


async def test_tiny_foreign_amount_allowed(
    db_session: Any, ledger: dict[str, uuid.UUID]
) -> None:
    """Мелкая сумма в слабой валюте не должна округляться в ноль."""
    db_session.add(
        _tx(
            ledger,
            account_id=ledger["uzs"],
            currency_code="UZS",
            amount=Decimal("-1000"),
            amount_rub=Decimal("-7.2000"),
            exchange_rate=Decimal("0.0072"),
        )
    )
    await db_session.flush()
