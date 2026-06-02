"""Pydantic-схемы домена transactions (обычные операции).

Переводы (kind=transfer) создаются отдельным доменом transfers.
Здесь только расход и доход в валюте своего счёта.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import RequiredKind, TransactionKind

__all__ = [
    "TransactionCreate",
    "TransactionRead",
    "TransactionUpdate",
]

OrdinaryKind = Literal[TransactionKind.EXPENSE, TransactionKind.INCOME]


class TransactionCreate(BaseModel):
    account_id: uuid.UUID
    kind: OrdinaryKind
    amount: Decimal = Field(gt=0)
    date: datetime
    category_id: uuid.UUID | None = None
    required: RequiredKind | None = None
    comment: str | None = None


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    date: datetime | None = None
    category_id: uuid.UUID | None = None
    required: RequiredKind | None = None
    comment: str | None = None


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    transfer_id: uuid.UUID | None
    kind: TransactionKind
    required: RequiredKind | None
    amount: Decimal
    currency_code: str
    amount_rub: Decimal
    exchange_rate: Decimal
    category_id: uuid.UUID | None
    date: datetime
    comment: str | None
    created_at: datetime
    updated_at: datetime
