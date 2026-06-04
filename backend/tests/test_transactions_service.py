"""Юнит-тесты TransactionService (signed amounts)."""

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
from app.domains.transactions.models import Transaction
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
)
from app.domains.transactions.service import TransactionService

USER = uuid.uuid4()
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeTxRepo:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Transaction] = {}

    async def list_page(self, user_id, flt):
        return list(self.items.values())

    async def get(self, tx_id, user_id):
        tx = self.items.get(tx_id)
        if tx is None or tx.user_id != user_id:
            return None
        return tx

    async def add(self, tx):
        if tx.id is None:
            tx.id = uuid.uuid4()
        self.items[tx.id] = tx
        return tx

    async def delete(self, tx):
        self.items.pop(tx.id, None)


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


def _account(code="RUB") -> Account:
    return Account(
        id=uuid.uuid4(),
        user_id=USER,
        name=f"Счёт {code}",
        type=AccountType.CARD,
        currency_code=code,
    )


def _category(kind=CategoryKind.EXPENSE) -> Category:
    return Category(
        id=uuid.uuid4(),
        user_id=USER,
        name="Еда",
        kind=kind,
        parent_id=None,
        is_archived=False,
    )


def _service(accounts, cats, rates):
    return TransactionService(
        FakeTxRepo(),
        FakeAccounts(accounts),
        FakeCategories(cats),
        FakeCurrencies(rates),
    )


async def test_expense_is_negative() -> None:
    acc = _account("RUB")
    svc = _service([acc], [], {})
    tx = await svc.create_transaction(
        USER,
        TransactionCreate(
            account_id=acc.id,
            kind=TransactionKind.EXPENSE,
            amount=Decimal("100"),
            date=NOW,
        ),
    )
    # расход хранится отрицательным
    assert tx.amount == Decimal("-100")
    assert tx.amount_rub == Decimal("-100")


async def test_income_is_positive() -> None:
    acc = _account("RUB")
    svc = _service([acc], [], {})
    tx = await svc.create_transaction(
        USER,
        TransactionCreate(
            account_id=acc.id,
            kind=TransactionKind.INCOME,
            amount=Decimal("1000"),
            date=NOW,
        ),
    )
    assert tx.amount == Decimal("1000")
    assert tx.amount_rub == Decimal("1000")


async def test_expense_usd_bakes_rate_signed() -> None:
    acc = _account("USD")
    svc = _service([acc], [], {"USD": Decimal("90")})
    tx = await svc.create_transaction(
        USER,
        TransactionCreate(
            account_id=acc.id,
            kind=TransactionKind.EXPENSE,
            amount=Decimal("5"),
            date=NOW,
        ),
    )
    assert tx.exchange_rate == Decimal("90")
    assert tx.amount == Decimal("-5")
    assert tx.amount_rub == Decimal("-450")


async def test_create_unknown_account() -> None:
    svc = _service([], [], {})
    with pytest.raises(NotFoundError):
        await svc.create_transaction(
            USER,
            TransactionCreate(
                account_id=uuid.uuid4(),
                kind=TransactionKind.EXPENSE,
                amount=Decimal("1"),
                date=NOW,
            ),
        )


async def test_create_category_kind_mismatch() -> None:
    acc = _account("RUB")
    income_cat = _category(CategoryKind.INCOME)
    svc = _service([acc], [income_cat], {})
    with pytest.raises(ValidationFailedError):
        await svc.create_transaction(
            USER,
            TransactionCreate(
                account_id=acc.id,
                kind=TransactionKind.EXPENSE,
                amount=Decimal("1"),
                date=NOW,
                category_id=income_cat.id,
            ),
        )


async def test_update_amount_keeps_sign() -> None:
    acc = _account("USD")
    svc = _service([acc], [], {"USD": Decimal("90")})
    tx = await svc.create_transaction(
        USER,
        TransactionCreate(
            account_id=acc.id,
            kind=TransactionKind.EXPENSE,
            amount=Decimal("5"),
            date=NOW,
        ),
    )
    # пользователь вводит положительное 10 — знак проставит сервис
    updated = await svc.update_transaction(
        tx.id, USER, TransactionUpdate(amount=Decimal("10"))
    )
    assert updated.exchange_rate == Decimal("90")
    assert updated.amount == Decimal("-10")
    assert updated.amount_rub == Decimal("-900")


async def test_get_missing() -> None:
    svc = _service([], [], {})
    with pytest.raises(NotFoundError):
        await svc.get_transaction(uuid.uuid4(), USER)
