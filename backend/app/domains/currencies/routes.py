"""HTTP-роуты валют: /currencies/*."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.schemas import ApiResponse
from app.domains.currencies.providers.er_api import (
    ErApiRatesProvider,
    RatesProvider,
)
from app.domains.currencies.repository import (
    CurrencyRepository,
    SqlCurrencyRepository,
)
from app.domains.currencies.schemas import (
    CurrencyRead,
    ExchangeRateRead,
    RefreshResult,
)
from app.domains.currencies.service import CurrencyService

router = APIRouter(prefix="/currencies", tags=["currencies"])


def get_currency_repository(db: DbSession) -> CurrencyRepository:
    return SqlCurrencyRepository(db)


def get_rates_provider(settings: SettingsDep) -> RatesProvider:
    return ErApiRatesProvider(settings)


def get_currency_service(
    repo: Annotated[CurrencyRepository, Depends(get_currency_repository)],
    provider: Annotated[RatesProvider, Depends(get_rates_provider)],
) -> CurrencyService:
    return CurrencyService(repo, provider)


CurrencyServiceDep = Annotated[CurrencyService, Depends(get_currency_service)]


@router.get("", response_model=ApiResponse[list[CurrencyRead]])
async def list_currencies(
    service: CurrencyServiceDep,
) -> ApiResponse[list[CurrencyRead]]:
    items = await service.list_currencies()
    return ApiResponse(data=[CurrencyRead.model_validate(c) for c in items])


@router.get("/rates", response_model=ApiResponse[list[ExchangeRateRead]])
async def list_rates(
    service: CurrencyServiceDep,
) -> ApiResponse[list[ExchangeRateRead]]:
    items = await service.list_rates()
    return ApiResponse(
        data=[ExchangeRateRead.model_validate(r) for r in items]
    )


@router.post("/rates/refresh", response_model=ApiResponse[RefreshResult])
async def refresh_rates(
    user: CurrentUser,
    service: CurrencyServiceDep,
    db: DbSession,
) -> ApiResponse[RefreshResult]:
    result = await service.refresh_rates()
    await db.commit()
    return ApiResponse(data=result)
