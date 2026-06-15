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
]


class AccountBalance(BaseModel):
    account_id: uuid.UUID
    name: str
    currency_code: str
    balance: Decimal  # в валюте счёта
    balance_rub: Decimal  # по текущему курсу


class DashboardResult(BaseModel):
    accounts: list[AccountBalance]
    total_capital_rub: Decimal


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
