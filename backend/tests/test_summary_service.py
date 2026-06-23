"""Юнит-тесты SummaryService на фейках."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.enums import AccountType
from app.core.exceptions import NotFoundError
from app.domains.accounts.models import Account
from app.domains.summary.service import SummaryService

USER = uuid.uuid4()


class FakeRepo:
    def __init__(self, accounts, balances, flow, spending):
        self._accounts = accounts
        self._balances = balances
        self._flow = flow
        self._spending = spending

    async def active_accounts(self, user_id):
        return self._accounts

    async def balances_by_account(self, user_id):
        return self._balances

    async def cashflow(self, user_id, date_from, date_to):
        return self._flow

    async def spending_by_category(self, user_id, date_from, date_to):
        return self._spending


class FakeCurrencies:
    def __init__(self, rates):
        self._r = rates

    async def rate_to_rub(self, code):
        if code == "RUB":
            return Decimal(1)
        rate = self._r.get(code)
        if rate is None:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return rate


def _acc(code, initial="0", name=None) -> Account:
    return Account(
        id=uuid.uuid4(),
        user_id=USER,
        name=name or f"Счёт {code}",
        type=AccountType.CARD,
        currency_code=code,
        initial_balance=Decimal(initial),
    )


async def test_dashboard_balance_and_capital() -> None:
    rub = _acc("RUB", initial="1000")
    usd = _acc("USD", initial="0")
    # по операциям: на RUB +500 (доход), на USD +10 (нога)
    balances = {rub.id: Decimal("500"), usd.id: Decimal("10")}
    svc = SummaryService(
        FakeRepo([rub, usd], balances, (Decimal(0), Decimal(0)), []),
        FakeCurrencies({"USD": Decimal("90")}),
    )
    res = await svc.dashboard(USER)
    by_id = {a.account_id: a for a in res.accounts}
    # RUB: 1000 + 500 = 1500, в рублях 1500
    assert by_id[rub.id].balance == Decimal("1500")
    assert by_id[rub.id].balance_rub == Decimal("1500")
    # USD: 0 + 10 = 10, в рублях 10*90 = 900
    assert by_id[usd.id].balance == Decimal("10")
    assert by_id[usd.id].balance_rub == Decimal("900")
    # капитал = 1500 + 900 = 2400
    assert res.total_capital_rub == Decimal("2400")
    assert res.is_total_complete is True
    assert res.missing_rate_currencies == []


async def test_dashboard_survives_missing_exchange_rate() -> None:
    rub = _acc("RUB", initial="1000")
    usd = _acc("USD", initial="10")
    svc = SummaryService(
        FakeRepo([rub, usd], {}, (Decimal(0), Decimal(0)), []),
        FakeCurrencies({}),
    )

    result = await svc.dashboard(USER)
    by_id = {item.account_id: item for item in result.accounts}

    assert by_id[rub.id].balance_rub == Decimal("1000")
    assert by_id[usd.id].balance == Decimal("10")
    assert by_id[usd.id].balance_rub is None
    assert result.total_capital_rub == Decimal("1000")
    assert result.is_total_complete is False
    assert result.missing_rate_currencies == ["USD"]


async def test_cashflow_expense_as_abs() -> None:
    # income +5000, expense -3000 (хранится отрицательным)
    svc = SummaryService(
        FakeRepo([], {}, (Decimal("5000"), Decimal("-3000")), []),
        FakeCurrencies({}),
    )
    res = await svc.cashflow(USER, date(2026, 1, 1), date(2026, 1, 31))
    assert res.income_rub == Decimal("5000")
    assert res.expense_rub == Decimal("3000")
    assert res.net_rub == Decimal("2000")


async def test_by_category_sorted_abs() -> None:
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()
    # расходы хранятся отрицательными
    spending = [(c1, Decimal("-200")), (c2, Decimal("-500"))]
    svc = SummaryService(
        FakeRepo([], {}, (Decimal(0), Decimal(0)), spending),
        FakeCurrencies({}),
    )
    res = await svc.by_category(USER, "2026-01")
    # отсортировано по убыванию, суммы положительные
    assert res.items[0].amount_rub == Decimal("500")
    assert res.items[1].amount_rub == Decimal("200")
    assert res.total_rub == Decimal("700")


async def test_by_category_bad_month() -> None:
    svc = SummaryService(
        FakeRepo([], {}, (Decimal(0), Decimal(0)), []),
        FakeCurrencies({}),
    )
    with pytest.raises(ValueError):
        await svc.by_category(USER, "2026-13")
