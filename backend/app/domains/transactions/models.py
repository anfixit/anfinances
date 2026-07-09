"""Модели транзакций и переводов.

Перевод/конвертация — две строки Transaction с общим transfer_id.
Комиссия — отдельная строка без transfer_id.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RequiredKind, TransactionKind
from app.core.models import Base, TimestampMixin, UUIDMixin


class Transfer(UUIDMixin, Base):
    """Группирующий узел для пары транзакций перевода."""

    __tablename__ = "transfers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Transaction(UUIDMixin, TimestampMixin, Base):
    """Транзакция: расход, доход или нога перевода."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_date", "user_id", "date"),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_transfer_id", "transfer_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transfers.id")
    )
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    kind: Mapped[TransactionKind] = mapped_column(
        PgEnum(TransactionKind, name="transaction_kind"),
        nullable=False,
    )
    required: Mapped[RequiredKind | None] = mapped_column(
        PgEnum(RequiredKind, name="required_kind")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    amount_rub: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    category_name_snapshot: Mapped[str | None] = mapped_column(String)
    subcategory_name_snapshot: Mapped[str | None] = mapped_column(String)
    account_name_snapshot: Mapped[str | None] = mapped_column(String)
    to_account_name_snapshot: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
