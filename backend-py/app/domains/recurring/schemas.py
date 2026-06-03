"""Pydantic-схемы домена recurring (план-минимум).

``amount_rub`` запекается сервисом при создании/обновлении из
``monthly_amount`` по текущему курсу; клиент его не передаёт.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RequiredKind

__all__ = [
    "RecurringCreate",
    "RecurringRead",
    "RecurringUpdate",
]


class RecurringCreate(BaseModel):
    # План-минимум по умолчанию — обязательные траты.
    required: RequiredKind = RequiredKind.REQUIRED
    category_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    monthly_amount: Decimal = Field(gt=0)
    currency_code: str = Field(default="RUB", min_length=3, max_length=3)
    comments: str | None = None


class RecurringUpdate(BaseModel):
    required: RequiredKind | None = None
    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    monthly_amount: Decimal | None = Field(default=None, gt=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    comments: str | None = None


class RecurringRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    required: RequiredKind | None
    category_id: uuid.UUID
    name: str
    monthly_amount: Decimal | None
    currency_code: str | None
    amount_rub: Decimal | None
    comments: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
