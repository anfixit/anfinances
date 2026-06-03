"""Pydantic-схемы домена users (профиль + валюты юзера).

``UserRead`` живёт в домене auth (владельце модели User) и
переиспользуется в роутах. Здесь — только схемы ввода профиля и
схемы валют юзера.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "UserCurrenciesUpdate",
    "UserCurrencyItem",
    "UserCurrencyRead",
    "UserUpdate",
]


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    default_currency: str | None = Field(
        default=None, min_length=3, max_length=3
    )
    locale: str | None = Field(default=None, min_length=2, max_length=16)


class UserCurrencyItem(BaseModel):
    currency_code: str = Field(min_length=3, max_length=3)
    is_default: bool = False
    sort_order: int = 0


class UserCurrenciesUpdate(BaseModel):
    items: list[UserCurrencyItem]


class UserCurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    currency_code: str
    is_default: bool
    sort_order: int
