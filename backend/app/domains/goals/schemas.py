"""Pydantic-схемы домена goals."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import GoalKind

__all__ = ["GoalRead", "GoalUpsert"]


class GoalUpsert(BaseModel):
    category_id: uuid.UUID
    kind: GoalKind
    amount: Decimal = Field(gt=0)
    target_date: date | None = None

    @model_validator(mode="after")
    def _check_date(self) -> "GoalUpsert":
        # Цель «к дате» без даты — это не цель, а пожелание; а дата у
        # ежемесячной цели ничего не значит и только путала бы.
        if self.kind == GoalKind.BY_DATE and self.target_date is None:
            raise ValueError("Для цели к дате нужна сама дата.")
        if self.kind == GoalKind.MONTHLY and self.target_date is not None:
            raise ValueError("У ежемесячной цели даты быть не может.")
        return self


class GoalRead(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    kind: GoalKind
    amount: Decimal
    target_date: date | None
    # Вычисляемое на запрошенный месяц.
    accumulated: Decimal
    need_this_month: Decimal
    planned_this_month: Decimal
    still_to_add: Decimal
    months_left: int
    is_reached: bool
    created_at: datetime
    updated_at: datetime
