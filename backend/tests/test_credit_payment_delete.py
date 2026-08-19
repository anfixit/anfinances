"""Удаление платежа по кредиту.

Удалить платёж было нельзя ниоткуда: обычное удаление операции
отказывало словами «кредитный платёж удаляется в домене кредитов»,
а в домене кредитов удаления не существовало. Задвоенный импортом
платёж застревал навсегда — и портил не только остаток счёта, но и
тело кредита, где погашение оказывалось засчитано дважды.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from app.core.exceptions import NotFoundError
from app.domains.credits.service import CreditService

USER = uuid.uuid4()


class _Credit:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.user_id = USER
        self.name = "Альфа Кредит"
        self.currency_code = "RUB"
        self.principal_initial = Decimal("685840")
        self.principal_balance = Decimal("175460.48")
        self.is_archived = False


class _Payment:
    def __init__(self, credit_id: uuid.UUID, principal: Decimal) -> None:
        self.id = uuid.uuid4()
        self.user_id = USER
        self.credit_id = credit_id
        self.transaction_id = uuid.uuid4()
        self.principal_amount = principal
        self.total_amount = principal
        self.date = datetime(2026, 7, 14, tzinfo=UTC)


class _Repo:
    def __init__(self, credit: _Credit, payment: _Payment | None) -> None:
        self._credit = credit
        self._payment = payment
        self.deleted_payments: list[_Payment] = []
        self.deleted_transactions: list[uuid.UUID] = []

    async def get(self, credit_id: uuid.UUID, user_id: uuid.UUID) -> _Credit:
        return self._credit

    async def get_payment(
        self, payment_id: uuid.UUID, user_id: uuid.UUID
    ) -> _Payment | None:
        return self._payment

    async def delete_payment(self, payment: _Payment) -> None:
        self.deleted_payments.append(payment)

    async def delete_transaction(self, tx_id: uuid.UUID) -> None:
        self.deleted_transactions.append(tx_id)


def _service(
    principal: Decimal = Decimal("20095.10"), missing: bool = False
) -> tuple[CreditService, _Credit, _Repo, _Payment]:
    credit = _Credit()
    payment = _Payment(credit.id, principal)
    repo = _Repo(credit, None if missing else payment)
    return (
        CreditService(cast(Any, repo), cast(Any, lambda: None)),
        credit,
        repo,
        payment,
    )


async def test_debt_comes_back() -> None:
    """Тело кредита обязано вернуться, иначе долг разойдётся с банком."""
    service, credit, _, payment = _service(Decimal("20095.10"))
    before = credit.principal_balance

    await service.delete_payment(payment.id, USER)

    assert credit.principal_balance == before + Decimal("20095.10")


async def test_payment_and_its_transaction_are_removed() -> None:
    """Списание со счёта живёт отдельной операцией — её тоже сносим."""
    service, _, repo, payment = _service()
    await service.delete_payment(payment.id, USER)

    assert repo.deleted_payments == [payment]
    assert repo.deleted_transactions == [payment.transaction_id]


async def test_missing_payment_is_reported() -> None:
    service, _, _, payment = _service(missing=True)
    with pytest.raises(NotFoundError):
        await service.delete_payment(payment.id, USER)
