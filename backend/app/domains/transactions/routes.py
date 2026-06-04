"""HTTP-роуты домена transactions.

router          — обычные операции /transactions/*
transfer_router — переводы /transfers/*
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.enums import TransactionKind
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import (
    ErApiRatesProvider,
)
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.repository import (
    SqlTransactionRepository,
    TransactionFilter,
)
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
    TransferCreate,
    TransferRead,
)
from app.domains.transactions.service import (
    TransactionService,
    TransferService,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])
transfer_router = APIRouter(prefix="/transfers", tags=["transfers"])


def _currencies(db: DbSession, settings: SettingsDep) -> CurrencyService:
    return CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )


def get_transaction_service(
    db: DbSession, settings: SettingsDep
) -> TransactionService:
    return TransactionService(
        SqlTransactionRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        _currencies(db, settings),
    )


def get_transfer_service(
    db: DbSession, settings: SettingsDep
) -> TransferService:
    return TransferService(
        SqlTransactionRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        _currencies(db, settings),
    )


TxServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
TransferServiceDep = Annotated[TransferService, Depends(get_transfer_service)]


# ── /transactions ────────────────────────────────────────────


@router.get("", response_model=ApiResponse[list[TransactionRead]])
async def list_transactions(
    user: CurrentUser,
    service: TxServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor_date: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    kind: TransactionKind | None = None,
) -> ApiResponse[list[TransactionRead]]:
    flt = TransactionFilter(
        limit=limit,
        cursor_date=cursor_date,
        cursor_id=cursor_id,
        date_from=date_from,
        date_to=date_to,
        account_id=account_id,
        category_id=category_id,
        kind=kind,
    )
    items = await service.list_transactions(user.id, flt)
    next_cursor = None
    if len(items) == limit:
        last = items[-1]
        next_cursor = {
            "cursor_date": last.date.isoformat(),
            "cursor_id": str(last.id),
        }
    return ApiResponse(
        data=[TransactionRead.model_validate(t) for t in items],
        meta={"next_cursor": next_cursor},
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TransactionRead],
)
async def create_transaction(
    data: TransactionCreate,
    user: CurrentUser,
    service: TxServiceDep,
    db: DbSession,
) -> ApiResponse[TransactionRead]:
    tx = await service.create_transaction(user.id, data)
    await db.commit()
    return ApiResponse(data=TransactionRead.model_validate(tx))


@router.get("/{tx_id}", response_model=ApiResponse[TransactionRead])
async def get_transaction(
    tx_id: uuid.UUID,
    user: CurrentUser,
    service: TxServiceDep,
) -> ApiResponse[TransactionRead]:
    tx = await service.get_transaction(tx_id, user.id)
    return ApiResponse(data=TransactionRead.model_validate(tx))


@router.patch("/{tx_id}", response_model=ApiResponse[TransactionRead])
async def update_transaction(
    tx_id: uuid.UUID,
    data: TransactionUpdate,
    user: CurrentUser,
    service: TxServiceDep,
    db: DbSession,
) -> ApiResponse[TransactionRead]:
    tx = await service.update_transaction(tx_id, user.id, data)
    await db.commit()
    return ApiResponse(data=TransactionRead.model_validate(tx))


@router.delete("/{tx_id}", response_model=ApiResponse[dict[str, str]])
async def delete_transaction(
    tx_id: uuid.UUID,
    user: CurrentUser,
    service: TxServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.delete_transaction(tx_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "deleted"})


# ── /transfers ───────────────────────────────────────────────


def _transfer_to_read(transfer_id: uuid.UUID, legs: list) -> TransferRead:
    return TransferRead.from_legs(
        transfer_id,
        [TransactionRead.model_validate(t) for t in legs],
    )


@transfer_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TransferRead],
)
async def create_transfer(
    data: TransferCreate,
    user: CurrentUser,
    service: TransferServiceDep,
    db: DbSession,
) -> ApiResponse[TransferRead]:
    transfer, legs = await service.create_transfer(user.id, data)
    await db.commit()
    return ApiResponse(data=_transfer_to_read(transfer.id, legs))


@transfer_router.get(
    "/{transfer_id}", response_model=ApiResponse[TransferRead]
)
async def get_transfer(
    transfer_id: uuid.UUID,
    user: CurrentUser,
    service: TransferServiceDep,
) -> ApiResponse[TransferRead]:
    transfer, legs = await service.get_transfer(transfer_id, user.id)
    return ApiResponse(data=_transfer_to_read(transfer.id, legs))


@transfer_router.delete(
    "/{transfer_id}",
    response_model=ApiResponse[dict[str, str]],
)
async def delete_transfer(
    transfer_id: uuid.UUID,
    user: CurrentUser,
    service: TransferServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.delete_transfer(transfer_id, user.id)
    await db.commit()
    return ApiResponse(data={"status": "deleted"})
