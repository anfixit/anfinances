"""HTTP-роуты бюджетов: /budgets/*.

Транзакцией управляет роут: сервис делает flush, успешный ответ
фиксируется commit (ADR-013). DELETE — физическое удаление
(в таблице budgets нет is_archived: запись дешёво пересоздать).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.budgets.repository import (
    BudgetRepository,
    SqlBudgetRepository,
)
from app.domains.budgets.schemas import (
    BudgetCreate,
    BudgetImport,
    BudgetRead,
    BudgetUpdate,
)
from app.domains.budgets.service import BudgetService
from app.domains.categories.repository import (
    CategoryRepository,
    SqlCategoryRepository,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])

_MONTH_PATTERN = r"^\d{4}-\d{2}$"


def get_budget_repository(db: DbSession) -> BudgetRepository:
    return SqlBudgetRepository(db)


def get_category_repository(db: DbSession) -> CategoryRepository:
    return SqlCategoryRepository(db)


def get_budget_service(
    repo: Annotated[BudgetRepository, Depends(get_budget_repository)],
    categories: Annotated[
        CategoryRepository, Depends(get_category_repository)
    ],
) -> BudgetService:
    return BudgetService(repo, categories)


ServiceDep = Annotated[BudgetService, Depends(get_budget_service)]


@router.get("", response_model=ApiResponse[list[BudgetRead]])
async def list_budgets(
    user: CurrentUser,
    service: ServiceDep,
    month: Annotated[str, Query(pattern=_MONTH_PATTERN)],
) -> ApiResponse[list[BudgetRead]]:
    items = await service.list_budgets(user.id, month, user.timezone)
    return ApiResponse(data=items)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[BudgetRead],
)
async def create_budget(
    data: BudgetCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[BudgetRead]:
    budget = await service.create_budget(
        user.id,
        data,
        user.timezone,
    )
    await db.commit()
    return ApiResponse(data=budget)


@router.post("/import", response_model=ApiResponse[list[BudgetRead]])
async def import_budgets(
    data: BudgetImport,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[list[BudgetRead]]:
    items = await service.import_budgets(
        user.id,
        data,
        user.timezone,
    )
    await db.commit()
    return ApiResponse(data=items)


@router.patch("/{budget_id}", response_model=ApiResponse[BudgetRead])
async def update_budget(
    budget_id: uuid.UUID,
    data: BudgetUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[BudgetRead]:
    budget = await service.update_budget(
        budget_id,
        user.id,
        data,
        user.timezone,
    )
    await db.commit()
    return ApiResponse(data=budget)


@router.delete("/{budget_id}", response_model=ApiResponse[dict[str, str]])
async def delete_budget(
    budget_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.delete_budget(budget_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "deleted"})
