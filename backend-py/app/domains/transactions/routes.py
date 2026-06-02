"""HTTP-роуты переводов: /transfers/*."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.repository import (
    SqlTransactionRepository,
)
from app.domains.transactions.schemas import (
    TransactionRead,
    TransferCreate,
    TransferRead,
)
from app.domains.transactions.transfer_service import TransferService

router = APIRouter(prefix="/transfers", tags=["transfers"])


def get_transfer_service(
    db: DbSession, settings: SettingsDep
) -> TransferService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    return TransferService(
        SqlTransactionRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        currencies,
    )


ServiceDep = Annotated[TransferService, Depends(get_transfer_service)]


def _to_read(transfer_id: uuid.UUID, legs: list) -> TransferRead:
    return TransferRead.from_legs(
        transfer_id,
        [TransactionRead.model_validate(t) for t in legs],
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TransferRead],
)
async def create_transfer(
    data: TransferCreate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[TransferRead]:
    transfer, legs = await service.create_transfer(user.id, data)
    await db.commit()
    return ApiResponse(data=_to_read(transfer.id, legs))


@router.get("/{transfer_id}", response_model=ApiResponse[TransferRead])
async def get_transfer(
    transfer_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[TransferRead]:
    transfer, legs = await service.get_transfer(transfer_id, user.id)
    return ApiResponse(data=_to_read(transfer.id, legs))


@router.delete(
    "/{transfer_id}",
    response_model=ApiResponse[dict[str, str]],
)
async def delete_transfer(
    transfer_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.delete_transfer(transfer_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "deleted"})
