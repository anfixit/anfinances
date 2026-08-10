"""Капитал уменьшается на остаток долга по кредитам.

Кредит — обязательство, а не счёт. Пока долг заведён счётом с
отрицательным балансом, итог верен сам собой. Как только кредит
переезжает в домен credits, капитал обязан вычитать его явно —
иначе показывает владельца богаче ровно на сумму долга.
"""

import uuid
from decimal import Decimal
from typing import Any, cast

from app.core.exceptions import NotFoundError
from app.domains.summary.service import SummaryService


class _Account:
    def __init__(self, name: str, currency: str, initial: Decimal) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.currency_code = currency
        self.initial_balance = initial


class _Credit:
    def __init__(self, currency: str, balance: Decimal) -> None:
        self.currency_code = currency
        self.principal_balance = balance


class _Repo:
    def __init__(
        self, accounts: list[_Account], credits: list[_Credit]
    ) -> None:
        self._accounts = accounts
        self._credits = credits

    async def active_accounts(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._accounts)

    async def balances_by_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]:
        return {}

    async def active_credits(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._credits)


class _Currencies:
    def __init__(self, known: dict[str, Decimal] | None = None) -> None:
        self._known = known or {
            "RUB": Decimal(1),
            "UZS": Decimal("0.0072"),
        }

    async def rate_to_rub(self, code: str) -> Decimal:
        if code not in self._known:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return self._known[code]


def _service(
    accounts: list[_Account],
    credits: list[_Credit],
    currencies: _Currencies | None = None,
) -> SummaryService:
    return SummaryService(
        cast(Any, _Repo(accounts, credits)),
        cast(Any, currencies or _Currencies()),
    )


async def test_debt_reduces_capital() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("100000"))],
        [_Credit("RUB", Decimal("280650.24"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal("280650.24")
    assert result.total_capital_rub == Decimal("-180650.24")


async def test_no_credits_leaves_capital_unchanged() -> None:
    service = _service([_Account("Альфа", "RUB", Decimal("1000"))], [])
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal(0)
    assert result.total_capital_rub == Decimal("1000")


async def test_foreign_currency_debt_is_converted() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("1000"))],
        [_Credit("UZS", Decimal("100000"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_credit_debt_rub == Decimal("720.0000")
    assert result.total_capital_rub == Decimal("280.0000")


async def test_new_loan_leaves_capital_flat() -> None:
    """Взяла кредит — деньги на счету и долг на ту же сумму."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("500000"))],
        [_Credit("RUB", Decimal("500000"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.total_capital_rub == Decimal("0")


async def test_missing_rate_for_debt_marks_total_incomplete() -> None:
    """Без курса долг не пересчитать — итог честно помечается неполным."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("1000"))],
        [_Credit("EUR", Decimal("100"))],
    )
    result = await service.dashboard(uuid.uuid4())
    assert result.is_total_complete is False
    assert "EUR" in result.missing_rate_currencies
