"""Pydantic-схемы домена transactions.

Обычные операции (расход/доход) и переводы (пара ног + комиссия).
TransactionRead объявлен раньше TransferRead, т.к. последний
ссылается на него в аннотациях.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.core.enums import RequiredKind, TransactionKind

__all__ = [
    "TransactionCreate",
    "TransactionRead",
    "TransactionUpdate",
    "TransferCreate",
    "TransferRead",
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


class TransferCreate(BaseModel):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount_from: Decimal = Field(gt=0)
    amount_to: Decimal = Field(gt=0)
    date: datetime
    comment: str | None = None
    fee_amount: Decimal | None = Field(default=None, gt=0)
    fee_category_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check(self) -> "TransferCreate":
        if self.from_account_id == self.to_account_id:
            raise ValueError("Счёт-источник и получатель должны различаться.")
        return self


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legs: list[TransactionRead]
    fee: TransactionRead | None = None

    @staticmethod
    def from_legs(
        transfer_id: uuid.UUID, txs: list[TransactionRead]
    ) -> "TransferRead":
        fee = next(
            (t for t in txs if t.kind == TransactionKind.EXPENSE),
            None,
        )
        legs = [t for t in txs if t.kind == TransactionKind.TRANSFER]
        return TransferRead(id=transfer_id, legs=legs, fee=fee)
