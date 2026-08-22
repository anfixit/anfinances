"""Модель получателя платежа.

Магазин раньше жил в свободном тексте комментария: «TAKSOPOLIS,
Москва», «п/п 672282, card2card с карты 9561». По такому не
сгруппировать и не найти. Отдельная сущность даёт три вещи: отчёт
«кому уходят деньги», память «этот получатель — эта категория» (по
ней выписка разносится без модели) и список тех, кого раньше не
было — так замечают забытую подписку и чужое списание.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Payee(UUIDMixin, TimestampMixin, Base):
    """Получатель платежа: магазин, сервис, человек."""

    __tablename__ = "payees"
    __table_args__ = (
        Index(
            "uq_payee_user_name_key",
            "user_id",
            "name_key",
            unique=True,
        ),
        Index("ix_payees_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Свёрнутое имя для сравнения: «ПЯТЕРОЧКА» и «пятерочка» — один
    # получатель. Считается в питоне, а не через lower() в SQL:
    # в SQLite lower() не трогает кириллицу, в PostgreSQL трогает, и
    # тогда тесты доказывали бы не то, что работает на проде.
    name_key: Mapped[str] = mapped_column(String, nullable=False)
    # Категория последней операции по этому получателю. Ею
    # подставляется категория при разносе следующей выписки.
    # ondelete=SET NULL: удалённая категория не должна ронять запись
    # получателя, подсказка просто исчезает.
    last_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
