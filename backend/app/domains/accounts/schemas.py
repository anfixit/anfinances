"""Pydantic-схемы домена accounts."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AccountType

__all__ = [
    "AccountCreate",
    "AccountRead",
    "AccountUpdate",
]


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: AccountType
    currency_code: str = Field(min_length=3, max_length=3)
    initial_balance: Decimal = Decimal("0")
    credit_limit: Decimal | None = None
    color: str | None = Field(default=None, max_length=32)
    sort_order: int = 0
    comments: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: AccountType | None = None
    initial_balance: Decimal | None = None
    credit_limit: Decimal | None = None
    color: str | None = Field(default=None, max_length=32)
    sort_order: int | None = None
    comments: str | None = None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: AccountType
    currency_code: str
    initial_balance: Decimal
    credit_limit: Decimal | None
    color: str | None
    sort_order: int
    comments: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
