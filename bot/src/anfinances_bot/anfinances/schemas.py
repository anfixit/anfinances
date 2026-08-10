"""Модели ответов anfinances API — только те поля, что нужны боту."""

from decimal import Decimal

from pydantic import BaseModel

__all__ = ["AccountRead", "CategoryRead", "UserProfile"]


class UserProfile(BaseModel):
    id: str
    email: str
    timezone: str
    default_currency: str


class AccountRead(BaseModel):
    id: str
    name: str
    currency_code: str
    current_balance: Decimal | None = None


class CategoryRead(BaseModel):
    id: str
    name: str
    kind: str
    parent_id: str | None = None
