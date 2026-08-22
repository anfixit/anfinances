"""HTTP-роуты сверки: /accounts/{id}/reconcile*."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.currencies.providers.er_api import ErApiRatesProvider
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService
from app.domains.reconciliation.repository import (
    SqlReconciliationRepository,
)
from app.domains.reconciliation.schemas import (
    ReconcileRequest,
    ReconciliationPreview,
    ReconciliationRead,
)
from app.domains.reconciliation.service import ReconciliationService
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.service import TransactionService

router = APIRouter(prefix="/accounts", tags=["reconciliation"])


def get_service(db: DbSession, settings: SettingsDep) -> ReconciliationService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    transactions = TransactionService(
        SqlTransactionRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        currencies,
        PayeeService(SqlPayeeRepository(db)),
    )
    return ReconciliationService(
        SqlReconciliationRepository(db),
        SqlAccountRepository(db),
        SqlCategoryRepository(db),
        transactions,
    )


ServiceDep = Annotated[ReconciliationService, Depends(get_service)]


@router.post(
    "/{account_id}/reconcile/preview",
    response_model=ApiResponse[ReconciliationPreview],
)
async def preview_reconciliation(
    account_id: uuid.UUID,
    data: ReconcileRequest,
    user: CurrentUser,
    service: ServiceDep,
) -> ApiResponse[ReconciliationPreview]:
    """Показать расхождение, ничего не меняя."""
    result = await service.preview(account_id, user.id, data)
    return ApiResponse(
        data=ReconciliationPreview(
            account_id=result.account_id,
            date=result.date,
            statement_balance=result.statement_balance,
            computed_balance=result.computed_balance,
            difference=result.difference,
            unreconciled_count=result.unreconciled_count,
        )
    )


@router.post(
    "/{account_id}/reconcile",
    response_model=ApiResponse[ReconciliationRead],
)
async def reconcile(
    account_id: uuid.UUID,
    data: ReconcileRequest,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[ReconciliationRead]:
    """Закрыть сверку. При расхождении требует adjust=true."""
    row = await service.reconcile(account_id, user.id, data)
    await db.commit()
    return ApiResponse(data=ReconciliationRead.model_validate(row))


@router.get(
    "/{account_id}/reconciliations",
    response_model=ApiResponse[list[ReconciliationRead]],
)
async def list_reconciliations(
    account_id: uuid.UUID, user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[ReconciliationRead]]:
    rows = await service.history(account_id, user.id)
    return ApiResponse(
        data=[ReconciliationRead.model_validate(r) for r in rows]
    )
