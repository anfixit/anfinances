"""Базовый класс моделей и общие миксины.

Base вынесен сюда из app.database, чтобы модели не зависели от
engine/session. app.database реэкспортирует Base для обратной
совместимости и для Alembic.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


class UUIDMixin:
    """Первичный ключ UUID, генерируется на стороне приложения."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Метки created_at / updated_at в UTC.

    created_at и updated_at проставляются БД (server_default=now()).
    updated_at обновляется на каждый UPDATE через onupdate.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
