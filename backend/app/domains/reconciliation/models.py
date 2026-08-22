"""Модель сверки счёта с выпиской банка.

Смысл сверки — поймать расхождение между тем, что записано, и тем,
что на самом деле в банке. Задвоенный платёж, потерянная трата,
перевод, у которого записали только одну ногу: всё это не видно в
списке операций, но сразу видно в остатке.

Отметка сверки на операциях говорит, до какого числа всё проверено.
Жёсткой блокировки правок нет: цена ошибочной блокировки — «не могу
исправить свои же данные», а это хуже, чем незамеченная правка
старого.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Reconciliation(UUIDMixin, TimestampMixin, Base):
    """Одна сверка: что показал банк и что было записано."""

    __tablename__ = "reconciliations"
    __table_args__ = (
        Index("ix_reconciliations_account_id", "account_id"),
        Index("ix_reconciliations_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    # На какой момент сверяли: остаток берётся по операциям до него.
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Что показал банк.
    statement_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    # Что было записано в anfinances на тот же момент.
    computed_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False
    )
    # Корректирующая операция, если расхождение закрыли ею, а не
    # поиском пропавшей записи.
    adjustment_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
