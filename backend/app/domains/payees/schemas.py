"""Pydantic-схемы домена payees."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.schemas import reject_nulls

__all__ = [
    "CandidateAccept",
    "PayeeCandidateRead",
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
    varied_categories: bool | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "PayeeUpdate":
        reject_nulls(self, ("name", "varied_categories"))
        return self


class PayeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    last_category_id: uuid.UUID | None
    varied_categories: bool
    created_at: datetime
    updated_at: datetime


class PayeeCandidateRead(BaseModel):
    """Имя в очереди разбора. ``amount`` считается на лету по операциям.

    В таблице не хранится: имя разбирают один раз, а лишнее поле
    пришлось бы держать в согласии с операциями.
    """

    id: uuid.UUID
    name: str
    times_seen: int
    amount: Decimal
    first_seen_at: datetime
    last_seen_at: datetime
    status: str


class CandidateAccept(BaseModel):
    # None — завести нового получателя; id — влить имя в существующего.
    payee_id: uuid.UUID | None = None


class PayeeSpending(BaseModel):
    payee_id: uuid.UUID
    name: str
    amount_rub: Decimal
    operations: int


class SpendingByPayee(BaseModel):
    month: str
    items: list[PayeeSpending]
    total_rub: Decimal
    # Имена, что ждут подтверждения: в items их нет, а деньги по ним
    # уходили. Строка под отчётом ведёт в очередь разбора.
    unsorted_names: int
    unsorted_amount: Decimal
