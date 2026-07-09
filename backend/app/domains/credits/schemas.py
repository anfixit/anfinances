"""Pydantic-схемы домена credits."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "CreditCreate",
    "CreditPaymentCreate",
    "CreditPaymentRead",
    "CreditRead",
    "CreditUpdate",
]


class CreditCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lender: str | None = Field(default=None, max_length=200)
    currency_code: str = Field(min_length=3, max_length=3)
    principal_initial: Decimal = Field(gt=0)
    annual_rate: Decimal | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    payment_day: int | None = Field(default=None, ge=1, le=31)
    linked_account_id: uuid.UUID | None = None
    comments: str | None = None


class CreditUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    lender: str | None = Field(default=None, max_length=200)
    principal_initial: Decimal | None = Field(default=None, gt=0)
    annual_rate: Decimal | None = Field(default=None, ge=0)
    term_months: int | None = Field(default=None, gt=0)
    start_date: date | None = None
    payment_day: int | None = Field(default=None, ge=1, le=31)
    linked_account_id: uuid.UUID | None = None
    comments: str | None = None


class CreditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    lender: str | None
    currency_code: str
    principal_initial: Decimal
    principal_balance: Decimal
    annual_rate: Decimal | None
    term_months: int | None
    start_date: date | None
    payment_day: int | None
    linked_account_id: uuid.UUID | None
    comments: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class CreditPaymentCreate(BaseModel):
    payment_account_id: uuid.UUID
    date: datetime
    total_amount: Decimal = Field(gt=0)
    principal_amount: Decimal = Field(ge=0)
    interest_amount: Decimal = Field(default=Decimal("0"), ge=0)
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    interest_category_id: uuid.UUID | None = None
    fee_category_id: uuid.UUID | None = None
    comment: str | None = None

    @model_validator(mode="after")
    def _check_parts(self) -> "CreditPaymentCreate":
        parts = self.principal_amount + self.interest_amount + self.fee_amount
        if parts != self.total_amount:
            raise ValueError(
                "Сумма платежа должна равняться телу, процентам и комиссии."
            )
        if parts == 0:
            raise ValueError("Платёж должен содержать ненулевую сумму.")
        return self


class CreditPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    credit_id: uuid.UUID
    payment_account_id: uuid.UUID
    transaction_id: uuid.UUID | None
    date: datetime
    total_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    fee_amount: Decimal
    currency_code: str
    interest_category_id: uuid.UUID | None
    fee_category_id: uuid.UUID | None
    comment: str | None
    created_at: datetime
    updated_at: datetime
