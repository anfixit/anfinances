"""Тесты схем кредитных платежей."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domains.credits.schemas import CreditPaymentCreate

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _payment(**kwargs: object) -> CreditPaymentCreate:
    data: dict[str, object] = {
        "payment_account_id": uuid.uuid4(),
        "date": NOW,
        "total_amount": Decimal("13395.51"),
        "principal_amount": Decimal("5415.70"),
        "interest_amount": Decimal("7979.81"),
        "fee_amount": Decimal("0"),
    }
    data.update(kwargs)
    return CreditPaymentCreate(**data)


def test_payment_parts_must_equal_total() -> None:
    with pytest.raises(ValidationError):
        _payment(interest_amount=Decimal("7979.80"))


def test_payment_accepts_real_bank_split() -> None:
    payment = _payment()

    assert payment.total_amount == Decimal("13395.51")
    assert payment.principal_amount == Decimal("5415.70")
    assert payment.interest_amount == Decimal("7979.81")
