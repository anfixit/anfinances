"""Pydantic-схемы домена currencies."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

__all__ = ["CurrencyRead", "ExchangeRateRead", "RefreshResult"]


class CurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    symbol: str | None
    decimals: int


class ExchangeRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_code: str
    quote_code: str
    rate: Decimal
    fetched_at: datetime


class RefreshResult(BaseModel):
    """Итог обновления курсов."""

    updated: int
    base: str
