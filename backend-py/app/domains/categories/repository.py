"""Доступ к БД для домена categories."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.categories.models import Category

__all__ = ["CategoryRepository", "SqlCategoryRepository"]


class CategoryRepository(Protocol):
    async def list_active(self, user_id: uuid.UUID) -> list[Category]: ...

    async def get(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> Category | None: ...

    async def get_active_sibling(
        self,
        user_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        name: str,
    ) -> Category | None: ...

    async def has_children(self, category_id: uuid.UUID) -> bool: ...

    async def add(self, category: Category) -> Category: ...


class SqlCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, user_id: uuid.UUID) -> list[Category]:
        result = await self._session.execute(
            select(Category)
            .where(
                Category.user_id == user_id,
                Category.is_archived.is_(False),
            )
            .order_by(Category.sort_order, Category.name)
        )
        return list(result.scalars().all())

    async def get(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> Category | None:
        result = await self._session.execute(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_sibling(
        self,
        user_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        name: str,
    ) -> Category | None:
        result = await self._session.execute(
            select(Category).where(
                Category.user_id == user_id,
                Category.parent_id == parent_id,
                Category.name == name,
                Category.is_archived.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def has_children(self, category_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(Category.id).where(
                Category.parent_id == category_id,
                Category.is_archived.is_(False),
            )
        )
        return result.first() is not None

    async def add(self, category: Category) -> Category:
        self._session.add(category)
        await self._session.flush()
        return category
