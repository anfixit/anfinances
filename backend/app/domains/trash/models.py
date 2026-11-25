"""Строка корзины — одно удаление целиком.

Перевод — это узел и две-три ноги, платёж по кредиту — строка платежа
и списание по счёту. В корзину они ложатся одной записью: вернуть
половину перевода нельзя, как нельзя и удалить половину.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDMixin

__all__ = ["DeletedRecord"]


class DeletedRecord(UUIDMixin, Base):
    __tablename__ = "deleted_records"
    __table_args__ = (
        Index("ix_deleted_records_user_deleted", "user_id", "deleted_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # transaction | transfer | credit_payment — строка, а не enum
    # PostgreSQL: новый вид не должен требовать миграции типа.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Что это было, словами — для списка на сайте и для ассистента.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Строки как были, по таблицам, в порядке вставки при возврате.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Кто удалил: «Сайт» или «ИИ: ChatGPT».
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    ai_connection_id: Mapped[uuid.UUID | None] = mapped_column()
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    restored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
