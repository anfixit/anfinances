"""Pydantic-схемы домена payees."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PayeeCreate",
    "PayeeRead",
    "PayeeSpending",
    "PayeeUpdate",
    "SpendingByPayee",
]


class PayeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PayeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class PayeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    last_category_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PayeeSpending(BaseModel):
    payee_id: uuid.UUID
    name: str
    amount_rub: Decimal
    operations: int


class SpendingByPayee(BaseModel):
    month: str
    items: list[PayeeSpending]
    total_rub: Decimal
