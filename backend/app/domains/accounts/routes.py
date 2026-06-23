"""HTTP-роуты счетов: /accounts/*."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import (
    AccountRepository,
    SqlAccountRepository,
)
from app.domains.accounts.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
)
from app.domains.accounts.service import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_account_repository(db: DbSession) -> AccountRepository:
    return SqlAccountRepository(db)


def get_account_service(
    repo: Annotated[AccountRepository, Depends(get_account_repository)],
) -> AccountService:
    return AccountService(repo)


ServiceDep = Annotated[AccountService, Depends(get_account_service)]


@router.get("", response_model=ApiResponse[list[AccountRead]])
async def list_accounts(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[AccountRead]]:
    items = await service.list_accounts(user.id)
    return ApiResponse(
        data=[
            AccountRead.from_account(
                item.account,
                item.current_balance,
            )
            for item in items
        ]
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AccountRead],
)
async def create_account(
    data: AccountCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[AccountRead]:
    account = await service.create_account(user.id, data)
    await db.commit()
    return ApiResponse(
        data=AccountRead.from_account(
            account,
            account.initial_balance,
        )
    )


@router.get("/{account_id}", response_model=ApiResponse[AccountRead])
async def get_account(
    account_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[AccountRead]:
    result = await service.get_account_result(account_id, user.id)
    return ApiResponse(
        data=AccountRead.from_account(
            result.account,
            result.current_balance,
        )
    )


@router.patch("/{account_id}", response_model=ApiResponse[AccountRead])
async def update_account(
    account_id: uuid.UUID,
    data: AccountUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[AccountRead]:
    account = await service.update_account(account_id, user.id, data)
    await db.commit()
    result = await service.get_account_result(account.id, user.id)
    return ApiResponse(
        data=AccountRead.from_account(
            result.account,
            result.current_balance,
        )
    )


@router.delete(
    "/{account_id}",
    response_model=ApiResponse[dict[str, str]],
)
async def delete_account(
    account_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.archive_account(account_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "archived"})


@router.post(
    "/{account_id}/restore",
    response_model=ApiResponse[AccountRead],
)
async def restore_account(
    account_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[AccountRead]:
    account = await service.restore_account(account_id, user.id)
    await db.commit()
    result = await service.get_account_result(account.id, user.id)
    return ApiResponse(
        data=AccountRead.from_account(
            result.account,
            result.current_balance,
        )
    )
