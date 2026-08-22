"""Доступ к БД для домена goals."""

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.goals.models import CategoryGoal

__all__ = ["GoalRepository", "SqlGoalRepository"]


class GoalRepository(Protocol):
    async def list_all(self, user_id: uuid.UUID) -> list[CategoryGoal]: ...

    async def get_by_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> CategoryGoal | None: ...

    async def add(self, goal: CategoryGoal) -> CategoryGoal: ...

    async def delete(self, goal: CategoryGoal) -> None: ...


class SqlGoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, user_id: uuid.UUID) -> list[CategoryGoal]:
        result = await self._session.execute(
            select(CategoryGoal).where(CategoryGoal.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> CategoryGoal | None:
        result = await self._session.execute(
            select(CategoryGoal).where(
                CategoryGoal.user_id == user_id,
                CategoryGoal.category_id == category_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, goal: CategoryGoal) -> CategoryGoal:
        self._session.add(goal)
        await self._session.flush()
        return goal

    async def delete(self, goal: CategoryGoal) -> None:
        await self._session.delete(goal)
