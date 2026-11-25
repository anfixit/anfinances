"""Pydantic-схемы домена users (профиль + валюты юзера).

``UserRead`` живёт в домене auth (владельце модели User) и
переиспользуется в роутах. Здесь — только схемы ввода профиля и
схемы валют юзера.
"""

import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.schemas import reject_nulls

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

    @model_validator(mode="after")
    def _no_nulls(self) -> "UserUpdate":
        reject_nulls(self, ("timezone", "default_currency", "locale"))
        return self


class UserCurrencyItem(BaseModel):
    currency_code: str = Field(min_length=3, max_length=3)
    sort_order: int = 0


class UserCurrenciesUpdate(BaseModel):
    items: list[UserCurrencyItem]


class UserCurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    currency_code: str
    sort_order: int
