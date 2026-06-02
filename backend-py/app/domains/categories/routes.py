"""HTTP-роуты категорий: /categories/*."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.categories.repository import (
    CategoryRepository,
    SqlCategoryRepository,
)
from app.domains.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)
from app.domains.categories.service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


def get_category_repository(db: DbSession) -> CategoryRepository:
    return SqlCategoryRepository(db)


def get_category_service(
    repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> CategoryService:
    return CategoryService(repo)


ServiceDep = Annotated[CategoryService, Depends(get_category_service)]


@router.get("", response_model=ApiResponse[list[CategoryRead]])
async def list_categories(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[CategoryRead]]:
    items = await service.list_categories(user.id)
    return ApiResponse(data=[CategoryRead.model_validate(c) for c in items])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CategoryRead],
)
async def create_category(
    data: CategoryCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[CategoryRead]:
    category = await service.create_category(user.id, data)
    await db.commit()
    return ApiResponse(data=CategoryRead.model_validate(category))


@router.get("/{category_id}", response_model=ApiResponse[CategoryRead])
async def get_category(
    category_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[CategoryRead]:
    category = await service.get_category(category_id, user.id)
    return ApiResponse(data=CategoryRead.model_validate(category))


@router.patch("/{category_id}", response_model=ApiResponse[CategoryRead])
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[CategoryRead]:
    category = await service.update_category(category_id, user.id, data)
    await db.commit()
    return ApiResponse(data=CategoryRead.model_validate(category))


@router.delete(
    "/{category_id}",
    response_model=ApiResponse[dict[str, str]],
)
async def delete_category(
    category_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.archive_category(category_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "archived"})
