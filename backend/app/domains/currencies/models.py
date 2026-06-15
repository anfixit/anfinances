"""Модели валют: справочник, активные валюты юзера, курсы."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin


class Currency(Base):
    """Глобальный справочник валют (ISO 4217). Сидится миграцией."""

    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String)
    decimals: Mapped[int] = mapped_column(
        Integer, default=2, server_default="2", nullable=False
    )


class UserCurrency(UUIDMixin, Base):
    """Какие валюты активны для конкретного юзера."""

    __tablename__ = "user_currencies"
    __table_args__ = (
        UniqueConstraint("user_id", "currency_code", name="uq_user_currency"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class ExchangeRate(UUIDMixin, Base):
    """Текущий курс пары валют. История — в transactions."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("base_code", "quote_code", name="uq_exchange_pair"),
    )

    base_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    quote_code: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
