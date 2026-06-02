"""Модель счёта пользователя."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import AccountType
from app.core.models import Base, TimestampMixin, UUIDMixin


class Account(UUIDMixin, TimestampMixin, Base):
    """Счёт: карта, наличные, кредитка, накопления, инвестиции."""

    __tablename__ = "accounts"
    __table_args__ = (
        Index(
            "uq_account_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("is_archived = false"),
        ),
        Index("ix_accounts_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[AccountType] = mapped_column(
        PgEnum(AccountType, name="account_type"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    initial_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    color: Mapped[str | None] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    comments: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
