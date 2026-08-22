"""Модель цели по категории.

Копилки уже есть: конверт с rollover копит остаток из месяца в месяц.
Чего не было — ответа на вопрос «сколько положить в этом месяце».
Его приходилось считать в голове, а значит не считать вовсе.

Цель отвечает на него сама: «нужно 60 000 к 1 декабря» превращается
во взнос текущего месяца, который остаётся только подтвердить.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import GoalKind
from app.core.models import Base, TimestampMixin, UUIDMixin


class CategoryGoal(UUIDMixin, TimestampMixin, Base):
    """Цель накопления по одной категории."""

    __tablename__ = "category_goals"
    __table_args__ = (
        # Одна цель на категорию: две цели на один конверт — это
        # два разных ответа на вопрос «сколько положить».
        UniqueConstraint(
            "user_id", "category_id", name="uq_goal_user_category"
        ),
        Index("ix_category_goals_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[GoalKind] = mapped_column(
        PgEnum(GoalKind, name="goal_kind"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Только для цели «к дате». У ежемесячной смысла не имеет.
    target_date: Mapped[date | None] = mapped_column(Date)
