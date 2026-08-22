"""Смену счёта у операции (AF-029).

«Записала не на тот счёт» — обычная ошибка, а исправить её было
нечем: `TransactionUpdate` счёт не принимал, приходилось удалять
операцию и заводить заново. При смене счёта может смениться валюта,
и тогда обязан пересчитаться рублёвый эквивалент — иначе сумовая
трата продолжит весить как рублёвая.

Курс при смене даты намеренно не трогается: истории курсов в системе
нет (решение Р-3), и «пересчёт» подставил бы сегодняшний курс, что
не ближе к истине, чем запечённый в момент записи.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from app.core.enums import TransactionKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.transactions.schemas import TransactionUpdate
from app.domains.transactions.service import TransactionService

USER = uuid.uuid4()
RUB_ACCOUNT = uuid.uuid4()
UZS_ACCOUNT = uuid.uuid4()
ALIEN_ACCOUNT = uuid.uuid4()


class _Account:
    def __init__(self, id_: uuid.UUID, name: str, code: str) -> None:
        self.id = id_
        self.name = name
        self.currency_code = code


class _Tx:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.user_id = USER
        self.account_id = RUB_ACCOUNT
        self.kind = TransactionKind.EXPENSE
        self.amount = Decimal("-500")
        self.currency_code = "RUB"
        self.amount_rub = Decimal("-500")
        self.exchange_rate = Decimal(1)
        self.date = datetime(2026, 8, 1, tzinfo=UTC)
        self.transfer_id = None
        self.category_id = None
        self.account_name_snapshot = "Альфа"


class _Repo:
    def __init__(self, tx: _Tx) -> None:
        self._tx = tx

    async def get(self, tx_id: uuid.UUID, user_id: uuid.UUID) -> _Tx:
        return self._tx


class _Accounts:
    def __init__(self) -> None:
        self._rows = {
            RUB_ACCOUNT: _Account(RUB_ACCOUNT, "Альфа", "RUB"),
            UZS_ACCOUNT: _Account(UZS_ACCOUNT, "Наличные сумы", "UZS"),
        }

    async def get(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> _Account | None:
        return self._rows.get(account_id)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return {"RUB": Decimal(1), "UZS": Decimal("0.0072")}[code]


def _service() -> tuple[TransactionService, _Tx]:
    tx = _Tx()
    service = TransactionService(
        cast(Any, _Repo(tx)),
        cast(Any, _Accounts()),
        cast(Any, None),
        cast(Any, _Currencies()),
        cast(Any, None),
    )
    return service, tx


async def test_account_can_be_changed() -> None:
    service, tx = _service()
    await service.update_transaction(
        tx.id, USER, TransactionUpdate(account_id=UZS_ACCOUNT)
    )
    assert tx.account_id == UZS_ACCOUNT
    assert tx.account_name_snapshot == "Наличные сумы"


async def test_currency_and_rate_follow_the_new_account() -> None:
    service, tx = _service()
    await service.update_transaction(
        tx.id, USER, TransactionUpdate(account_id=UZS_ACCOUNT)
    )
    assert tx.currency_code == "UZS"
    assert tx.exchange_rate == Decimal("0.0072")
    # Сумма в валюте не меняется, меняется её рублёвая оценка.
    assert tx.amount == Decimal("-500")
    assert tx.amount_rub == Decimal("-3.6000")


async def test_same_currency_keeps_the_baked_rate() -> None:
    """Перенос между рублёвыми счетами курс трогать не должен."""
    service, tx = _service()
    tx.exchange_rate = Decimal("1")
    await service.update_transaction(
        tx.id, USER, TransactionUpdate(account_id=RUB_ACCOUNT)
    )
    assert tx.exchange_rate == Decimal("1")
    assert tx.amount_rub == Decimal("-500")


async def test_alien_account_is_rejected() -> None:
    service, tx = _service()
    with pytest.raises(NotFoundError):
        await service.update_transaction(
            tx.id, USER, TransactionUpdate(account_id=ALIEN_ACCOUNT)
        )
    assert tx.account_id == RUB_ACCOUNT


async def test_date_change_keeps_the_baked_rate() -> None:
    """Истории курсов нет — «пересчёт» подставил бы сегодняшний."""
    service, tx = _service()
    await service.update_transaction(
        tx.id,
        USER,
        TransactionUpdate(date=datetime(2025, 1, 1, tzinfo=UTC)),
    )
    assert tx.exchange_rate == Decimal(1)
    assert tx.amount_rub == Decimal("-500")


async def test_amount_and_account_change_together() -> None:
    service, tx = _service()
    await service.update_transaction(
        tx.id,
        USER,
        TransactionUpdate(account_id=UZS_ACCOUNT, amount=Decimal("1000")),
    )
    assert tx.amount == Decimal("-1000")
    assert tx.amount_rub == Decimal("-7.2000")


async def test_transfer_leg_still_cannot_be_edited() -> None:
    service, tx = _service()
    tx.transfer_id = uuid.uuid4()
    with pytest.raises(ValidationFailedError):
        await service.update_transaction(
            tx.id, USER, TransactionUpdate(account_id=UZS_ACCOUNT)
        )
