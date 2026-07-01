"""HTTP-роуты регулярных платежей: /recurring/*.

Транзакцией управляет роут: сервис делает flush, успешный ответ
фиксируется commit (ADR-013). DELETE — архивирование (ADR-010).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.recurring.repository import SqlRecurringRepository
from app.domains.recurring.schemas import (
    RecurringCreate,
    RecurringRead,
    RecurringUpdate,
)
from app.domains.recurring.service import RecurringService

router = APIRouter(prefix="/recurring", tags=["recurring"])


def get_recurring_service(
    db: DbSession, settings: SettingsDep
) -> RecurringService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    return RecurringService(
        SqlRecurringRepository(db),
        SqlCategoryRepository(db),
        currencies,
    )


ServiceDep = Annotated[RecurringService, Depends(get_recurring_service)]


@router.get("", response_model=ApiResponse[list[RecurringRead]])
async def list_recurring(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[RecurringRead]]:
    items = await service.list_recurring(user.id)
    return ApiResponse(data=[RecurringRead.model_validate(i) for i in items])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[RecurringRead],
)
async def create_recurring(
    data: RecurringCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[RecurringRead]:
    item = await service.create_recurring(user.id, data)
    await db.commit()
    return ApiResponse(data=RecurringRead.model_validate(item))


@router.post(
    "/generate-from-categories",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[list[RecurringRead]],
)
async def generate_from_categories(
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[list[RecurringRead]]:
    items = await service.generate_from_categories(
        user.id,
        user.timezone,
    )
    await db.commit()
    return ApiResponse(data=[RecurringRead.model_validate(i) for i in items])


@router.patch("/{recurring_id}", response_model=ApiResponse[RecurringRead])
async def update_recurring(
    recurring_id: uuid.UUID,
    data: RecurringUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[RecurringRead]:
    item = await service.update_recurring(recurring_id, user.id, data)
    await db.commit()
    return ApiResponse(data=RecurringRead.model_validate(item))


@router.delete("/{recurring_id}", response_model=ApiResponse[dict[str, str]])
async def delete_recurring(
    recurring_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.archive_recurring(recurring_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "archived"})
