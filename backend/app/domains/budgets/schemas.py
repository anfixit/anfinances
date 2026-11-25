"""Pydantic-схемы домена budgets.

``month`` в API — строка ``'YYYY-MM'``; в БД хранится как ``date``
(первое число месяца). Поля ``rollover_amount``, ``available``,
``spent``, ``remaining`` — вычисляемые, в БД не хранятся.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.money import Money
from app.core.schemas import reject_nulls

__all__ = [
    "BudgetCreate",
    "BudgetMove",
    "BudgetImport",
    "BudgetImportItem",
    "BudgetRead",
    "BudgetUpdate",
]

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class BudgetCreate(BaseModel):
    month: str = Field(pattern=_MONTH_PATTERN)
    category_id: uuid.UUID
    planned: Money = Field(ge=0)
    notes: str | None = None
    rollover: bool = False


class BudgetUpdate(BaseModel):
    planned: Money | None = Field(default=None, ge=0)
    notes: str | None = None
    rollover: bool | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "BudgetUpdate":
        reject_nulls(self, ("planned", "rollover"))
        return self


class BudgetImportItem(BaseModel):
    category_id: uuid.UUID
    planned: Money = Field(ge=0)
    notes: str | None = None
    rollover: bool = False


class BudgetImport(BaseModel):
    month: str = Field(pattern=_MONTH_PATTERN)
    items: list[BudgetImportItem]


class BudgetMove(BaseModel):
    """Перенос части плана между категориями внутри месяца."""

    month: str = Field(pattern=_MONTH_PATTERN)
    from_category_id: uuid.UUID
    to_category_id: uuid.UUID
    amount: Money = Field(gt=0)


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
