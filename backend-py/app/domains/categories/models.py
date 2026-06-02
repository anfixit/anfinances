"""Модель категории (с иерархией через parent_id)."""

import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import CategoryKind
from app.core.models import Base, TimestampMixin, UUIDMixin


class Category(UUIDMixin, TimestampMixin, Base):
    """Категория транзакций. Дерево через self-FK parent_id."""

    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_category_user_parent_name_active",
            "user_id",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("is_archived = false"),
        ),
        Index("ix_categories_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    icon: Mapped[str | None] = mapped_column(String)
    kind: Mapped[CategoryKind] = mapped_column(
        PgEnum(CategoryKind, name="category_kind"), nullable=False
    )
    is_archived: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
