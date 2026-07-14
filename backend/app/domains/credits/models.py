"""Модели кредитов и платежей по ним.

Кредит хранится отдельно от Account: это долговое обязательство,
а не счёт с деньгами. Платёж связан со служебной Transaction,
которая списывает полную сумму со счёта. Расходом считаются только
проценты и комиссии, а тело уменьшает основной долг.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Credit(UUIDMixin, TimestampMixin, Base):
    """Кредитный договор и текущий остаток основного долга."""

    __tablename__ = "credits"
    __table_args__ = (
        Index(
            "uq_credit_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_archived = false"),
        ),
        Index("ix_credits_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    lender: Mapped[str | None] = mapped_column(String)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    principal_initial: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    principal_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    annual_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    term_months: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    payment_day: Mapped[int | None] = mapped_column(Integer)
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id")
    )
    comments: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )


class CreditPayment(UUIDMixin, TimestampMixin, Base):
    """Расшифровка одного платежа: тело, проценты и комиссии."""

    __tablename__ = "credit_payments"
    __table_args__ = (
        Index("ix_credit_payments_user_date", "user_id", "date"),
        Index("ix_credit_payments_credit_date", "credit_id", "date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    credit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("credits.id"), nullable=False
    )
    payment_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id")
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    interest_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    interest_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    fee_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    comment: Mapped[str | None] = mapped_column(Text)
