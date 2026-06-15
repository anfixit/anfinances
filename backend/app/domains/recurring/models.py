"""Модель регулярного платежа (plan_min)."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RequiredKind
from app.core.models import Base, TimestampMixin, UUIDMixin


class RecurringExpense(UUIDMixin, TimestampMixin, Base):
    """Регулярный ежемесячный платёж по категории."""

    __tablename__ = "recurring_expenses"
    __table_args__ = (Index("ix_recurring_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    required: Mapped[RequiredKind | None] = mapped_column(
        PgEnum(RequiredKind, name="required_kind")
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    monthly_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str | None] = mapped_column(
        String(3), ForeignKey("currencies.code")
    )
    amount_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    comments: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
