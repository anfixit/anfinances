"""FastAPI-приложение: точка входа.

Собирает: настройки → middleware → exception handlers → роуты.
Бизнес-логика лежит в app/domains/* и подключается роутерами
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, status
from sqlalchemy import text

from app.config import get_settings
from app.core.dependencies import DbSession
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware
from app.database import AsyncSessionLocal, engine
from app.domains.accounts.routes import router as accounts_router
from app.domains.auth.bootstrap import bootstrap_single_user
from app.domains.auth.routes import router as auth_router
from app.domains.budgets.routes import router as budgets_router
from app.domains.categories.routes import router as categories_router
from app.domains.currencies.routes import router as currencies_router
from app.domains.summary.routes import router as summary_router
from app.domains.transactions.routes import (
    router as transactions_router,
)
from app.domains.transactions.routes import (
    transfer_router,
)

logger = logging.getLogger("anfinances")


# ── Lifespan: startup и shutdown ─────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Жизненный цикл приложения.

    На старте: проверяем подключение к БД (fail fast если она недоступна).
    На остановке: корректно закрываем пул соединений.
    """
    settings = get_settings()

    logger.info(
        "Starting %s in %s mode (auth_mode=%s)",
        settings.project_name,
        settings.environment,
        settings.auth_mode,
    )

    # Smoke-тест БД на старте.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as exc:
        logger.error("Database connection failed at startup: %s", exc)
        # Не падаем: приложение поднимется, /health/ready даст не-ready.
        # Это удобнее в docker-compose: контейнер не уходит в restart-loop.

    try:
        async with AsyncSessionLocal() as session:
            await bootstrap_single_user(session, settings)
    except Exception as exc:
        logger.error("single_user bootstrap failed: %s", exc)

    try:
        async with AsyncSessionLocal() as session:
            from app.domains.currencies.providers.er_api import (
                ErApiRatesProvider,
            )
            from app.domains.currencies.repository import (
                SqlCurrencyRepository,
            )
            from app.domains.currencies.service import CurrencyService

            svc = CurrencyService(
                SqlCurrencyRepository(session),
                ErApiRatesProvider(settings),
            )

            await svc.refresh_rates()
            await session.commit()

            logger.info("Currency rates refreshed on startup")

    except Exception as exc:
        logger.warning(
            "Rates refresh on startup failed: %s",
            exc,
        )

    yield

    await engine.dispose()
    logger.info("Database engine disposed")


# ── Health-роутер ────────────────────────────────────────────────────

health_router = APIRouter(tags=["health"])


@health_router.get(
    "/health/live",
    summary="Liveness probe",
    response_model=dict[str, str],
)
async def health_live() -> dict[str, str]:
    """Просто отвечает что процесс жив. Не трогает БД.

    Используется для k8s liveness, docker healthcheck и т.п.
    """
    return {"status": "ok"}


@health_router.get(
    "/health/ready",
    summary="Readiness probe (with DB check)",
    response_model=dict[str, Any],
)
async def health_ready(db: DbSession) -> dict[str, Any]:
    """Проверяет что приложение готово обслуживать запросы.

    Делает SELECT 1 к БД. Если БД лежит — возвращает 503.
    """
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)

        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not available",
        ) from exc

    return {"status": "ok", "database": "ok"}


# Алиас /health = /health/ready — для удобства curl-проверки из задания.
@health_router.get("/health", include_in_schema=False)
async def health(db: DbSession) -> dict[str, Any]:
    return await health_ready(db)


# ── Создание приложения ──────────────────────────────────────────────


def create_app() -> FastAPI:
    """Фабрика приложения. Удобно для тестов с другими settings."""
    settings = get_settings()

    app = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Личный финансовый трекер. См. ARCHITECTURE.md.",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        openapi_url=(
            f"{settings.api_v1_prefix}/openapi.json"
            if settings.environment != "production"
            else None
        ),
    )

    register_middleware(app, settings)
    register_exception_handlers(app)

    # Health endpoints — под /api/v1.
    app.include_router(health_router, prefix=settings.api_v1_prefix)

    app.include_router(auth_router, prefix=settings.api_v1_prefix)

    app.include_router(currencies_router, prefix=settings.api_v1_prefix)

    app.include_router(accounts_router, prefix=settings.api_v1_prefix)

    app.include_router(categories_router, prefix=settings.api_v1_prefix)

    app.include_router(transactions_router, prefix=settings.api_v1_prefix)

    app.include_router(transfer_router, prefix=settings.api_v1_prefix)

    app.include_router(summary_router, prefix=settings.api_v1_prefix)

    app.include_router(budgets_router, prefix=settings.api_v1_prefix)

    return app


# Объект, который запускает uvicorn: `uvicorn app.main:app`.
app = create_app()

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
