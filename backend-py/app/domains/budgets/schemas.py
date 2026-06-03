"""Pydantic-схемы домена budgets.

``month`` в API — строка ``'YYYY-MM'``; в БД хранится как ``date``
(первое число месяца). Поля ``rollover_amount``, ``available``,
``spent``, ``remaining`` — вычисляемые, в БД не хранятся.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

__all__ = [
    "BudgetCreate",
    "BudgetImport",
    "BudgetImportItem",
    "BudgetRead",
    "BudgetUpdate",
]

_MONTH_PATTERN = r"^\d{4}-\d{2}$"


class BudgetCreate(BaseModel):
    month: str = Field(pattern=_MONTH_PATTERN)
    category_id: uuid.UUID
    planned: Decimal = Field(ge=0)
    notes: str | None = None
    rollover: bool = False


class BudgetUpdate(BaseModel):
    planned: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
    rollover: bool | None = None


class BudgetImportItem(BaseModel):
    category_id: uuid.UUID
    planned: Decimal = Field(ge=0)
    notes: str | None = None
    rollover: bool = False


class BudgetImport(BaseModel):
    month: str = Field(pattern=_MONTH_PATTERN)
    items: list[BudgetImportItem]


class BudgetRead(BaseModel):
    id: uuid.UUID
    month: str
    category_id: uuid.UUID
    planned: Decimal
    notes: str | None
    rollover: bool
    rollover_amount: Decimal
    available: Decimal
    spent: Decimal
    remaining: Decimal
    created_at: datetime
    updated_at: datetime
