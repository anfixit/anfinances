"""HTTP-обвязка эндпоинтов для ассистента: доходы, платежи, план.

Логика проверена на уровне сервисов. Здесь — что маршруты
подключены, параметры валидируются, а /credits/payoff-plan не
перехватывается маршрутом /credits/{credit_id}.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings
from app.core import dependencies as deps
from app.core.models import Base
from app.database import get_db
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL

STRONG = "fluffy-zebra-canyon-marble-97"


class _FakePwned:
    async def assert_not_pwned(self, plain: str) -> None:
        return None


@pytest_asyncio.fixture
async def api():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    options: dict[str, object] = {
        "secret_key": "x" * 64,
        "auth_mode": "multi_user_no_verify",
        "hibp_enabled": False,
    }
    settings = Settings(**options)  # type: ignore[arg-type]
    app = create_app()

    async def _override_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_pwned_checker] = lambda: _FakePwned()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as ac:
        reg = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        token = reg.json()["data"]["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
    await engine.dispose()


async def test_income_by_category_route(api: AsyncClient) -> None:
    r = await api.get(
        "/api/v1/summary/income-by-category", params={"month": "2026-09"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {
        "month": "2026-09",
        "items": [],
        "total_rub": "0",
    }

    bad = await api.get(
        "/api/v1/summary/income-by-category", params={"month": "2026-9"}
    )
    assert bad.status_code == 422


async def test_upcoming_payments_route(api: AsyncClient) -> None:
    r = await api.get("/api/v1/summary/upcoming-payments")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == []

    for days in (0, 93):
        bad = await api.get(
            "/api/v1/summary/upcoming-payments", params={"days": days}
        )
        assert bad.status_code == 422


async def test_payoff_plan_route_is_not_a_credit_id(api: AsyncClient) -> None:
    r = await api.get(
        "/api/v1/credits/payoff-plan",
        params={"strategy": "snowball", "extra_monthly": "5000.50"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["strategy"] == "snowball"
    assert data["order"] == []
    assert data["skipped"] == []
    assert data["baseline"]["months_to_debt_free"] == 0

    for params in (
        {"strategy": "random"},
        {"extra_monthly": "-1"},
    ):
        bad = await api.get("/api/v1/credits/payoff-plan", params=params)
        assert bad.status_code == 422
