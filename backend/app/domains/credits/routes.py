"""HTTP-роуты домена credits."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.credits.repository import (
    CreditRepository,
    SqlCreditRepository,
)
from app.domains.credits.schemas import (
    CreditCreate,
    CreditPaymentCreate,
    CreditPaymentRead,
    CreditRead,
    CreditUpdate,
)
from app.domains.credits.service import CreditService
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.repository import SqlTransactionRepository

router = APIRouter(prefix="/credits", tags=["credits"])


def get_credit_repository(db: DbSession) -> CreditRepository:
    return SqlCreditRepository(db)


def get_credit_service(
    repo: Annotated[CreditRepository, Depends(get_credit_repository)],
    db: DbSession,
    settings: SettingsDep,
) -> CreditService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    return CreditService(
        repo,
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        SqlTransactionRepository(db),
        currencies,
    )


ServiceDep = Annotated[CreditService, Depends(get_credit_service)]


@router.get("", response_model=ApiResponse[list[CreditRead]])
async def list_credits(
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[list[CreditRead]]:
    items = await service.list_credits(user.id)
    return ApiResponse(
        data=[CreditRead.model_validate(item) for item in items]
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CreditRead],
)
async def create_credit(
    data: CreditCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[CreditRead]:
    credit = await service.create_credit(user.id, data)
    await db.commit()
    return ApiResponse(data=CreditRead.model_validate(credit))


@router.get("/{credit_id}", response_model=ApiResponse[CreditRead])
async def get_credit(
    credit_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[CreditRead]:
    credit = await service.get_credit(credit_id, user.id)
    return ApiResponse(data=CreditRead.model_validate(credit))


@router.patch("/{credit_id}", response_model=ApiResponse[CreditRead])
async def update_credit(
    credit_id: uuid.UUID,
    data: CreditUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[CreditRead]:
    credit = await service.update_credit(credit_id, user.id, data)
    await db.commit()
    return ApiResponse(data=CreditRead.model_validate(credit))


@router.delete(
    "/{credit_id}",
    response_model=ApiResponse[dict[str, str]],
)
async def delete_credit(
    credit_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.archive_credit(credit_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "archived"})


@router.get(
    "/{credit_id}/payments",
    response_model=ApiResponse[list[CreditPaymentRead]],
)
async def list_credit_payments(
    credit_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[list[CreditPaymentRead]]:
    payments = await service.list_payments(credit_id, user.id)
    return ApiResponse(
        data=[CreditPaymentRead.model_validate(item) for item in payments]
    )


@router.post(
    "/{credit_id}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CreditPaymentRead],
)
async def create_credit_payment(
    credit_id: uuid.UUID,
    data: CreditPaymentCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[CreditPaymentRead]:
    payment = await service.create_payment(credit_id, user.id, data)
    await db.commit()
    return ApiResponse(data=CreditPaymentRead.model_validate(payment))
