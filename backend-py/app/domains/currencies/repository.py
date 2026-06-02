"""Доступ к БД для домена currencies."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.currencies.models import Currency, ExchangeRate

__all__ = ["CurrencyRepository", "SqlCurrencyRepository"]


class CurrencyRepository(Protocol):
    async def list_currencies(self) -> list[Currency]: ...

    async def list_rates(self) -> list[ExchangeRate]: ...

    async def get_rate(
        self, base_code: str, quote_code: str
    ) -> ExchangeRate | None: ...

    async def upsert_rate(
        self, base_code: str, quote_code: str, rate: Decimal
    ) -> None: ...


class SqlCurrencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_currencies(self) -> list[Currency]:
        result = await self._session.execute(
            select(Currency).order_by(Currency.code)
        )
        return list(result.scalars().all())

    async def list_rates(self) -> list[ExchangeRate]:
        result = await self._session.execute(select(ExchangeRate))
        return list(result.scalars().all())

    async def get_rate(
        self, base_code: str, quote_code: str
    ) -> ExchangeRate | None:
        result = await self._session.execute(
            select(ExchangeRate).where(
                ExchangeRate.base_code == base_code,
                ExchangeRate.quote_code == quote_code,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_rate(
        self, base_code: str, quote_code: str, rate: Decimal
    ) -> None:
        existing = await self.get_rate(base_code, quote_code)
        if existing is None:
            self._session.add(
                ExchangeRate(
                    base_code=base_code,
                    quote_code=quote_code,
                    rate=rate,
                )
            )
        else:
            existing.rate = rate
            existing.fetched_at = datetime.now(UTC)
        await self._session.flush()
