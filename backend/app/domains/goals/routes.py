"""HTTP-роуты целей: /goals/*."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.budgets.repository import SqlBudgetRepository
from app.domains.budgets.service import BudgetService
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.goals.repository import SqlGoalRepository
from app.domains.goals.schemas import GoalRead, GoalUpsert
from app.domains.goals.service import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])

_MONTH_PATTERN = r"^\d{4}-\d{2}$"


def get_service(db: DbSession) -> GoalService:
    return GoalService(SqlGoalRepository(db), SqlCategoryRepository(db))


def get_budgets(db: DbSession) -> BudgetService:
    return BudgetService(SqlBudgetRepository(db), SqlCategoryRepository(db))


ServiceDep = Annotated[GoalService, Depends(get_service)]
BudgetsDep = Annotated[BudgetService, Depends(get_budgets)]


@router.get("", response_model=ApiResponse[list[GoalRead]])
async def list_goals(
    user: CurrentUser,
    service: ServiceDep,
    budgets: BudgetsDep,
    month: Annotated[str, Query(pattern=_MONTH_PATTERN)],
) -> ApiResponse[list[GoalRead]]:
    """Цели вместе с расчётом взноса на указанный месяц."""
    views = await budgets.list_budgets(user.id, month, user.timezone)
    year, mon = (int(part) for part in month.split("-"))
    rows = await service.progress(user.id, date(year, mon, 1), views)
    return ApiResponse(
        data=[
            GoalRead(
                id=row.goal.id,
                category_id=row.goal.category_id,
                kind=row.goal.kind,
                amount=row.goal.amount,
                target_date=row.goal.target_date,
                accumulated=row.accumulated,
                need_this_month=row.need_this_month,
                planned_this_month=row.planned_this_month,
                still_to_add=row.still_to_add,
                months_left=row.months_left,
                is_reached=row.is_reached,
                created_at=row.goal.created_at,
                updated_at=row.goal.updated_at,
            )
            for row in rows
        ]
    )


@router.put("", response_model=ApiResponse[dict[str, str]])
async def upsert_goal(
    data: GoalUpsert,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    """Поставить или заменить цель по категории."""
    goal = await service.upsert_goal(user.id, data)
    await db.commit()
    return ApiResponse(data={"id": str(goal.id)})


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    category_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> None:
    await service.delete_goal(user.id, category_id)
    await db.commit()
