"""Модель месячного бюджета по категории."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Budget(UUIDMixin, TimestampMixin, Base):
    """План расходов на месяц по категории.

    rollover_amount не хранится — считается на лету в сервисе.
    """

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            "category_id",
            name="uq_budget_user_month_category",
        ),
        Index("ix_budgets_user_month", "user_id", "month"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )
    planned: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    rollover: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
