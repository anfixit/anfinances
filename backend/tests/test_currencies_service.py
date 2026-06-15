"""Юнит-тесты CurrencyService на фейках."""

from decimal import Decimal

import pytest

from app.core.exceptions import NotFoundError
from app.domains.currencies.models import Currency, ExchangeRate
from app.domains.currencies.service import CurrencyService


class FakeRepo:
    def __init__(self) -> None:
        self.currencies: list[Currency] = []
        self.rates: dict[tuple[str, str], ExchangeRate] = {}

    async def list_currencies(self) -> list[Currency]:
        return self.currencies

    async def list_rates(self) -> list[ExchangeRate]:
        return list(self.rates.values())

    async def get_rate(self, base, quote) -> ExchangeRate | None:
        return self.rates.get((base, quote))

    async def upsert_rate(self, base, quote, rate) -> None:
        self.rates[(base, quote)] = ExchangeRate(
            base_code=base, quote_code=quote, rate=rate
        )


class FakeProvider:
    def __init__(self, data: dict[str, Decimal]) -> None:
        self._data = data

    async def fetch_rates(self, base: str) -> dict[str, Decimal]:
        return self._data


def _cur(code: str) -> Currency:
    return Currency(code=code, name=code, symbol=None, decimals=2)


@pytest.fixture
def repo() -> FakeRepo:
    r = FakeRepo()
    r.rates[("USD", "RUB")] = ExchangeRate(
        base_code="USD", quote_code="RUB", rate=Decimal("90")
    )
    r.rates[("EUR", "RUB")] = ExchangeRate(
        base_code="EUR", quote_code="RUB", rate=Decimal("100")
    )
    return r


async def test_convert_same_currency(repo: FakeRepo) -> None:
    svc = CurrencyService(repo, FakeProvider({}))
    assert await svc.convert(Decimal("5"), "USD", "USD") == Decimal("5")


async def test_convert_to_rub(repo: FakeRepo) -> None:
    svc = CurrencyService(repo, FakeProvider({}))
    assert await svc.convert(Decimal("10"), "USD", "RUB") == Decimal("900")


async def test_convert_from_rub(repo: FakeRepo) -> None:
    svc = CurrencyService(repo, FakeProvider({}))
    assert await svc.convert(Decimal("900"), "RUB", "USD") == Decimal("10")


async def test_convert_cross(repo: FakeRepo) -> None:
    svc = CurrencyService(repo, FakeProvider({}))
    # 100 USD -> 9000 RUB -> 90 EUR
    assert await svc.convert(Decimal("100"), "USD", "EUR") == Decimal("90")


async def test_convert_missing_rate(repo: FakeRepo) -> None:
    svc = CurrencyService(repo, FakeProvider({}))
    with pytest.raises(NotFoundError):
        await svc.convert(Decimal("1"), "GBP", "RUB")


async def test_refresh_inverts_rate() -> None:
    repo = FakeRepo()
    repo.currencies = [_cur("RUB"), _cur("USD")]
    # провайдер: 1 RUB = 0.01 USD  =>  1 USD = 100 RUB
    provider = FakeProvider({"USD": Decimal("0.01")})
    svc = CurrencyService(repo, provider)
    result = await svc.refresh_rates()
    assert result.updated == 1
    assert repo.rates[("USD", "RUB")].rate == Decimal("100")
