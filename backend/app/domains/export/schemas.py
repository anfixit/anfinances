"""Pydantic-схемы домена export.

«Сырые» строки таблиц для полного бэкапа (``all.json``) — собственный
стабильный формат, не зависящий от Read-схем доменов, чтобы бэкап не
ломался при изменении API. Все суммы — строками, даты — ISO
(``model_dump(mode="json")``).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AccountType,
    CategoryKind,
    GoalKind,
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
    # Поля версии 2. У бэкапа версии 1 их нет — отсюда умолчания.
    payee_id: uuid.UUID | None = None
    payee_name_snapshot: str | None = None
    category_name_snapshot: str | None = None
    subcategory_name_snapshot: str | None = None
    account_name_snapshot: str | None = None
    to_account_name_snapshot: str | None = None
    reconciled_at: datetime | None = None


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


class ExportCredit(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    name: str
    lender: str | None
    currency_code: str
    principal_initial: Decimal
    principal_balance: Decimal
    annual_rate: Decimal | None
    term_months: int | None
    monthly_payment: Decimal | None
    start_date: date | None
    payment_day: int | None
    linked_account_id: uuid.UUID | None
    comments: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ExportCreditPayment(BaseModel):
    model_config = _RAW

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


class ExportPayee(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    name: str
    last_category_id: uuid.UUID | None
    varied_categories: bool
    created_at: datetime
    updated_at: datetime


class ExportGoal(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    category_id: uuid.UUID
    kind: GoalKind
    amount: Decimal
    target_date: date | None
    created_at: datetime
    updated_at: datetime


class ExportReconciliation(BaseModel):
    model_config = _RAW

    id: uuid.UUID
    account_id: uuid.UUID
    date: datetime
    statement_balance: Decimal
    computed_balance: Decimal
    adjustment_transaction_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExportBundle(BaseModel):
    """Полный бэкап данных юзера.

    Версия 1 знала только счета, категории, переводы, операции,
    бюджеты и план-минимум. Всё появившееся позже — кредиты с
    платежами, получатели, цели и сверки — в версии 2. Без них
    восстановленные платежи по кредиту висели без самого кредита:
    ни поправить, ни удалить, а долг пропадал из капитала.
    Бэкап версии 1 по-прежнему восстанавливается — новые списки
    в нём просто пустые.
    """

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
    credits: list[ExportCredit] = Field(default_factory=list)
    credit_payments: list[ExportCreditPayment] = Field(default_factory=list)
    payees: list[ExportPayee] = Field(default_factory=list)
    goals: list[ExportGoal] = Field(default_factory=list)
    reconciliations: list[ExportReconciliation] = Field(default_factory=list)
