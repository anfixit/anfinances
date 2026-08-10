"""Схемы домена summary (только чтение, без таблиц)."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

__all__ = [
    "AccountBalance",
    "CashflowResult",
    "ByCategoryResult",
    "CategorySpending",
    "DashboardResult",
    "MoneyAgeResult",
]


class AccountBalance(BaseModel):
    account_id: uuid.UUID
    name: str
    currency_code: str
    balance: Decimal  # в валюте счёта
    balance_rub: Decimal | None  # по текущему курсу, если доступен


class DashboardResult(BaseModel):
    accounts: list[AccountBalance]
    total_capital_rub: Decimal
    is_total_complete: bool
    missing_rate_currencies: list[str]


class CashflowResult(BaseModel):
    date_from: date
    date_to: date
    income_rub: Decimal
    expense_rub: Decimal
    net_rub: Decimal


class CategorySpending(BaseModel):
    category_id: uuid.UUID | None
    amount_rub: Decimal  # положительная сумма расхода


class ByCategoryResult(BaseModel):
    month: str
    items: list[CategorySpending]
    total_rub: Decimal


class MoneyAgeResult(BaseModel):
    """Насколько траты текущего месяца покрыты доходом прошлого.

    Четвёртое правило ВНБ: жить на доход предыдущего месяца.
    ``coverage`` — доля: 1.0 значит ровно покрыто, больше — запас,
    ``None`` — трат в текущем месяце ещё не было.
    """

    previous_month: str
    current_month: str
    previous_month_income_rub: Decimal
    current_month_expense_rub: Decimal
    coverage: Decimal | None
    is_covered: bool
