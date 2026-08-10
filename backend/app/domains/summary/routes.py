"""HTTP-роуты сводок: /summary/*."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.currencies.providers.er_api import (
    ErApiRatesProvider,
)
from app.domains.currencies.repository import SqlCurrencyRepository
from app.domains.currencies.service import CurrencyService
from app.domains.summary.repository import SqlSummaryRepository
from app.domains.summary.schemas import (
    ByCategoryResult,
    CashflowResult,
    DailyAllowanceResult,
    DashboardResult,
    MoneyAgeResult,
)
from app.domains.summary.service import SummaryService

router = APIRouter(prefix="/summary", tags=["summary"])


def get_summary_service(
    db: DbSession, settings: SettingsDep
) -> SummaryService:
    currencies = CurrencyService(
        SqlCurrencyRepository(db),
        ErApiRatesProvider(settings),
    )
    return SummaryService(SqlSummaryRepository(db), currencies)


ServiceDep = Annotated[SummaryService, Depends(get_summary_service)]


@router.get("/money-age", response_model=ApiResponse[MoneyAgeResult])
async def money_age(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[MoneyAgeResult]:
    """Насколько траты месяца покрыты доходом предыдущего."""
    result = await service.money_age(user.id, user.timezone)
    return ApiResponse(data=result)


@router.get(
    "/daily-allowance",
    response_model=ApiResponse[DailyAllowanceResult],
)
async def daily_allowance(
    user: CurrentUser,
    service: ServiceDep,
    until: date | None = None,
) -> ApiResponse[DailyAllowanceResult]:
    """Сколько можно тратить в день, не сорвав обязательства."""
    result = await service.daily_allowance(user.id, user.timezone, until)
    return ApiResponse(data=result)


@router.get("/dashboard", response_model=ApiResponse[DashboardResult])
async def dashboard(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[DashboardResult]:
    result = await service.dashboard(user.id)
    return ApiResponse(data=result)


@router.get("/cashflow", response_model=ApiResponse[CashflowResult])
async def cashflow(
    user: CurrentUser,
    service: ServiceDep,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> ApiResponse[CashflowResult]:
    result = await service.cashflow(
        user.id,
        date_from,
        date_to,
        user.timezone,
    )
    return ApiResponse(data=result)


@router.get("/by-category", response_model=ApiResponse[ByCategoryResult])
async def by_category(
    user: CurrentUser,
    service: ServiceDep,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
) -> ApiResponse[ByCategoryResult]:
    result = await service.by_category(user.id, month, user.timezone)
    return ApiResponse(data=result)
