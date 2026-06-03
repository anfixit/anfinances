"""Pydantic-схемы домена export.

«Сырые» строки таблиц для полного бэкапа (``all.json``) — собственный
стабильный формат, не зависящий от Read-схем доменов, чтобы бэкап не
ломался при изменении API. Все суммы — строками, даты — ISO
(``model_dump(mode="json")``).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.core.enums import (
    AccountType,
    CategoryKind,
    RequiredKind,
    TransactionKind,
)

__all__ = ["ExportBundle"]

_RAW = ConfigDict(from_attributes=True)


class ExportUser(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    email: str
    name: str | None
    timezone: str
    default_currency: str
    locale: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class ExportUserCurrency(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    currency_code: str
    is_default: bool
    sort_order: int


class ExportAccount(BaseModel):
    model_config = _RAW

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


class ExportCategory(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    icon: str | None
    kind: CategoryKind
    is_archived: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ExportTransfer(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    created_at: datetime


class ExportTransaction(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    transfer_id: uuid.UUID | None
    date: datetime
    kind: TransactionKind
    required: RequiredKind | None
    amount: Decimal
    currency_code: str
    amount_rub: Decimal
    exchange_rate: Decimal
    account_id: uuid.UUID
    category_id: uuid.UUID | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ExportBudget(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    month: date
    category_id: uuid.UUID
    planned: Decimal
    notes: str | None
    rollover: bool
    created_at: datetime
    updated_at: datetime


class ExportRecurring(BaseModel):
    model_config = _RAW

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


class ExportBundle(BaseModel):
    """Полный бэкап данных юзера. version — для будущего import."""

    version: int
    exported_at: datetime
    user: ExportUser
    currencies: list[ExportUserCurrency]
    accounts: list[ExportAccount]
    categories: list[ExportCategory]
    transfers: list[ExportTransfer]
    transactions: list[ExportTransaction]
    budgets: list[ExportBudget]
    recurring: list[ExportRecurring]
