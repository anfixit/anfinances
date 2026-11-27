"""HTTP-роуты импорта: /import/*.

Транзакцией управляет роут (ADR-013): весь импорт — в одной БД-
транзакции, commit только при полном успехе, иначе откат целиком.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.export.schemas import ExportBundle
from app.domains.import_.caching import (
    CachedAccountRepository,
    CachedCategoryRepository,
    CachedCurrencyService,
    CachedPayeeService,
)
from app.domains.import_.repository import SqlImportRepository
from app.domains.import_.schemas import ImportResult, ImportTransactions
from app.domains.import_.service import ImportService
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.service import TransactionService

router = APIRouter(prefix="/import", tags=["import"])


def get_import_service(db: DbSession, settings: SettingsDep) -> ImportService:
    # Репозитории и сервисы с памятью на один запрос: выписка в тысячу
    # строк иначе тысячу раз спрашивает у базы один и тот же счёт,
    # категорию, получателя и курс. См. caching.py.
    currencies = CachedCurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    transactions = TransactionService(
        SqlTransactionRepository(db),
        CachedAccountRepository(db),
        CachedCategoryRepository(db),
        currencies,
        CachedPayeeService(SqlPayeeRepository(db)),
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
