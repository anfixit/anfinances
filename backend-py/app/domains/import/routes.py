"""HTTP-роуты импорта: /import/*.

Транзакцией управляет роут (ADR-013): весь импорт — в одной БД-
транзакции, commit только при полном успехе, иначе откат целиком.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.export.schemas import ExportBundle
from app.domains.import_.repository import SqlImportRepository
from app.domains.import_.schemas import ImportResult, ImportTransactions
from app.domains.import_.service import ImportService
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.service import TransactionService

router = APIRouter(prefix="/import", tags=["import"])


def get_import_service(db: DbSession, settings: SettingsDep) -> ImportService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    transactions = TransactionService(
        SqlTransactionRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        currencies,
    )
    return ImportService(SqlImportRepository(db), transactions)


ServiceDep = Annotated[ImportService, Depends(get_import_service)]


@router.post(
    "/transactions",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[dict[str, int]],
)
async def import_transactions(
    data: ImportTransactions,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, int]]:
    created = await service.import_transactions(user.id, data.items)
    await db.commit()
    return ApiResponse(data={"created": created})


@router.post(
    "/all",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ImportResult],
)
async def import_all(
    data: ExportBundle,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[ImportResult]:
    result = await service.restore_all(user.id, data)
    await db.commit()
    return ApiResponse(data=result)
