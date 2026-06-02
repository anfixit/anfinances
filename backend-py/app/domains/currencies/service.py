"""Бизнес-логика валют: конвертация и обновление курсов.

Курсы хранятся как «сколько RUB за 1 единицу валюты»
(base_code=валюта, quote_code=RUB). Тогда:
    amount_rub = amount * rate.
Провайдер (open.er-api.com) при base=RUB отдаёт обратное
(сколько валюты за 1 RUB), поэтому инвертируем: rate = 1 / x.
"""

from decimal import Decimal

from app.core.exceptions import NotFoundError
from app.domains.currencies.models import Currency, ExchangeRate
from app.domains.currencies.providers.er_api import (
    RatesProvider,
)
from app.domains.currencies.repository import CurrencyRepository
from app.domains.currencies.schemas import RefreshResult

__all__ = ["CurrencyService"]

_BASE = "RUB"


class CurrencyService:
    def __init__(
        self,
        repo: CurrencyRepository,
        provider: RatesProvider,
    ) -> None:
        self._repo = repo
        self._provider = provider

    async def list_currencies(self) -> list[Currency]:
        return await self._repo.list_currencies()

    async def list_rates(self) -> list[ExchangeRate]:
        return await self._repo.list_rates()

    async def convert(
        self, amount: Decimal, from_code: str, to_code: str
    ) -> Decimal:
        """Сконвертировать сумму между валютами через RUB."""
        if from_code == to_code:
            return amount

        rub = amount * await self._rate_to_rub(from_code)
        if to_code == _BASE:
            return rub
        return rub / await self._rate_to_rub(to_code)

    async def _rate_to_rub(self, code: str) -> Decimal:
        if code == _BASE:
            return Decimal(1)
        rate = await self._repo.get_rate(code, _BASE)
        if rate is None:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return rate.rate

    async def refresh_rates(self) -> RefreshResult:
        """Обновить курсы всех валют справочника относительно RUB."""
        raw = await self._provider.fetch_rates(_BASE)
        currencies = await self._repo.list_currencies()

        updated = 0
        for currency in currencies:
            code = currency.code
            if code == _BASE:
                continue
            per_rub = raw.get(code)
            if per_rub is None or per_rub == 0:
                continue
            await self._repo.upsert_rate(code, _BASE, Decimal(1) / per_rub)
            updated += 1

        return RefreshResult(updated=updated, base=_BASE)
