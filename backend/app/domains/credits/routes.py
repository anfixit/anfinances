"""HTTP-роуты домена credits."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.credits.repository import (
    CreditRepository,
    SqlCreditRepository,
)
from app.domains.credits.schemas import (
    CreditCreate,
    CreditRead,
    CreditUpdate,
)
from app.domains.credits.service import CreditService

router = APIRouter(prefix="/credits", tags=["credits"])


def get_credit_repository(db: DbSession) -> CreditRepository:
    return SqlCreditRepository(db)


def get_credit_service(
    repo: Annotated[CreditRepository, Depends(get_credit_repository)],
    db: DbSession,
) -> CreditService:
    return CreditService(repo, SqlAccountRepository(db))


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
