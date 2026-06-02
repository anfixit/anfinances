"""Юнит-тесты TransferService (signed amounts)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums import (
    AccountType,
    CategoryKind,
    TransactionKind,
)
from app.core.exceptions import (
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.models import Account
from app.domains.categories.models import Category
from app.domains.transactions.models import Transaction, Transfer
from app.domains.transactions.schemas import TransferCreate
from app.domains.transactions.service import TransferService

USER = uuid.uuid4()
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeTxRepo:
    def __init__(self) -> None:
        self.txs: list[Transaction] = []
        self.transfers: dict[uuid.UUID, Transfer] = {}

    async def add(self, tx):
        if tx.id is None:
            tx.id = uuid.uuid4()
        self.txs.append(tx)
        return tx

    async def delete(self, tx):
        self.txs = [t for t in self.txs if t.id != tx.id]

    async def add_transfer(self, transfer):
        if transfer.id is None:
            transfer.id = uuid.uuid4()
        self.transfers[transfer.id] = transfer
        return transfer

    async def get_transfer(self, transfer_id, user_id):
        t = self.transfers.get(transfer_id)
        if t is None or t.user_id != user_id:
            return None
        return t

    async def list_transfer_legs(self, transfer_id):
        return [t for t in self.txs if t.transfer_id == transfer_id]


class FakeAccounts:
    def __init__(self, accounts):
        self._a = {a.id: a for a in accounts}

    async def get(self, account_id, user_id):
        a = self._a.get(account_id)
        if a is None or a.user_id != user_id:
            return None
        return a


class FakeCategories:
    def __init__(self, cats):
        self._c = {c.id: c for c in cats}

    async def get(self, category_id, user_id):
        c = self._c.get(category_id)
        if c is None or c.user_id != user_id:
            return None
        return c


class FakeCurrencies:
    def __init__(self, rates):
        self._r = rates

    async def rate_to_rub(self, code):
        if code == "RUB":
            return Decimal(1)
        return self._r[code]


def _acc(code, name=None) -> Account:
    return Account(
        id=uuid.uuid4(),
        user_id=USER,
        name=name or f"Счёт {code}",
        type=AccountType.CARD,
        currency_code=code,
    )


def _service(accounts, cats, rates):
    return TransferService(
        FakeTxRepo(),
        FakeAccounts(accounts),
        FakeCategories(cats),
        FakeCurrencies(rates),
    )


async def test_transfer_signs_and_balance() -> None:
    src = _acc("RUB")
    dst = _acc("USD")
    svc = _service([src, dst], [], {"USD": Decimal("90")})
    _, legs = await svc.create_transfer(
        USER,
        TransferCreate(
            from_account_id=src.id,
            to_account_id=dst.id,
            amount_from=Decimal("9500"),
            amount_to=Decimal("100"),
            date=NOW,
        ),
    )
    src_leg = next(t for t in legs if t.account_id == src.id)
    dst_leg = next(t for t in legs if t.account_id == dst.id)
    # источник отрицателен, получатель положителен
    assert src_leg.amount == Decimal("-9500")
    assert src_leg.amount_rub == Decimal("-9500")
    assert dst_leg.amount == Decimal("100")
    assert dst_leg.amount_rub == Decimal("9500")
    # фактический курс получателя = 9500 / 100 = 95
    assert dst_leg.exchange_rate == Decimal("95")
    # перевод в рублях нулевой: сумма amount_rub ног = 0
    assert src_leg.amount_rub + dst_leg.amount_rub == Decimal("0")


async def test_transfer_same_currency() -> None:
    src = _acc("RUB", "A")
    dst = _acc("RUB", "B")
    svc = _service([src, dst], [], {})
    _, legs = await svc.create_transfer(
        USER,
        TransferCreate(
            from_account_id=src.id,
            to_account_id=dst.id,
            amount_from=Decimal("1000"),
            amount_to=Decimal("1000"),
            date=NOW,
        ),
    )
    src_leg = next(t for t in legs if t.account_id == src.id)
    dst_leg = next(t for t in legs if t.account_id == dst.id)
    assert src_leg.amount == Decimal("-1000")
    assert dst_leg.amount == Decimal("1000")


async def test_transfer_with_fee_negative() -> None:
    src = _acc("RUB")
    dst = _acc("USD")
    fee_cat = Category(
        id=uuid.uuid4(),
        user_id=USER,
        name="Обслуживание",
        kind=CategoryKind.EXPENSE,
        parent_id=None,
        is_archived=False,
    )
    svc = _service([src, dst], [fee_cat], {"USD": Decimal("90")})
    _, created = await svc.create_transfer(
        USER,
        TransferCreate(
            from_account_id=src.id,
            to_account_id=dst.id,
            amount_from=Decimal("9500"),
            amount_to=Decimal("100"),
            date=NOW,
            fee_amount=Decimal("50"),
            fee_category_id=fee_cat.id,
        ),
    )
    assert len(created) == 3
    fee = next(t for t in created if t.kind == TransactionKind.EXPENSE)
    assert fee.amount == Decimal("-50")
    assert fee.amount_rub == Decimal("-50")
    assert fee.category_id == fee_cat.id
    assert fee.account_id == src.id


async def test_fee_category_wrong_kind() -> None:
    src = _acc("RUB")
    dst = _acc("USD")
    income_cat = Category(
        id=uuid.uuid4(),
        user_id=USER,
        name="Зарплата",
        kind=CategoryKind.INCOME,
        parent_id=None,
        is_archived=False,
    )
    svc = _service([src, dst], [income_cat], {"USD": Decimal("90")})
    with pytest.raises(ValidationFailedError):
        await svc.create_transfer(
            USER,
            TransferCreate(
                from_account_id=src.id,
                to_account_id=dst.id,
                amount_from=Decimal("9500"),
                amount_to=Decimal("100"),
                date=NOW,
                fee_amount=Decimal("50"),
                fee_category_id=income_cat.id,
            ),
        )


async def test_transfer_unknown_account() -> None:
    src = _acc("RUB")
    svc = _service([src], [], {})
    with pytest.raises(NotFoundError):
        await svc.create_transfer(
            USER,
            TransferCreate(
                from_account_id=src.id,
                to_account_id=uuid.uuid4(),
                amount_from=Decimal("100"),
                amount_to=Decimal("100"),
                date=NOW,
            ),
        )


async def test_delete_transfer_removes_legs() -> None:
    src = _acc("RUB")
    dst = _acc("USD")
    svc = _service([src, dst], [], {"USD": Decimal("90")})
    transfer, _ = await svc.create_transfer(
        USER,
        TransferCreate(
            from_account_id=src.id,
            to_account_id=dst.id,
            amount_from=Decimal("9500"),
            amount_to=Decimal("100"),
            date=NOW,
        ),
    )
    await svc.delete_transfer(transfer.id, USER)
    _, legs = await svc.get_transfer(transfer.id, USER)
    assert legs == []
