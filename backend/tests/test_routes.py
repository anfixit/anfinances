"""Интеграционные тесты /auth/* и /config через httpx + SQLite.

Refresh-токен ходит в HttpOnly-cookie, поэтому base_url — https
(иначе httpx не отдаёт Secure-cookie обратно).
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


class FakePwned:
    async def assert_not_pwned(self, plain: str) -> None:
        return None


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "secret_key": "x" * 64,
        "auth_mode": "multi_user_no_verify",
        "hibp_enabled": False,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def client_factory():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    def make(settings: Settings) -> AsyncClient:
        app = create_app()

        async def _override_db():
            async with sessionmaker() as session:
                yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[deps.get_pwned_checker] = lambda: FakePwned()
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
        )

    yield make
    await engine.dispose()


async def test_register_login_me_flow(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        r = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        access = data["access_token"]
        assert access
        assert "refresh_token" not in data  # refresh — только в cookie
        assert r.cookies.get("refresh_token")

        r = await ac.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["email"] == "a@b.com"


async def test_register_forbidden_in_single_user(
    client_factory,
) -> None:
    async with client_factory(_settings(auth_mode="single_user")) as ac:
        r = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        assert r.status_code == 403


async def test_login_wrong_password(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        r = await ac.post(
            "/api/v1/auth/login",
            json={"email": "a@b.com", "password": "wrong-xyz-123"},
        )
        assert r.status_code == 401


async def test_refresh_rotation_flow(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        reg = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        old = reg.cookies.get("refresh_token")
        assert old

        # Cookie уходит из jar автоматически.
        r2 = await ac.post("/api/v1/auth/refresh")
        assert r2.status_code == 200, r2.text
        new = r2.cookies.get("refresh_token")
        assert new and new != old

        # Старый refresh после ротации отозван.
        ac.cookies.clear()
        r3 = await ac.post(
            "/api/v1/auth/refresh",
            headers={"Cookie": f"refresh_token={old}"},
        )
        assert r3.status_code == 401


async def test_refresh_without_cookie(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        r = await ac.post("/api/v1/auth/refresh")
        assert r.status_code == 401


async def test_me_requires_auth(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        r = await ac.get("/api/v1/auth/me")
        assert r.status_code == 401


async def test_logout_invalidates_refresh(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        out = await ac.post("/api/v1/auth/logout")
        assert out.status_code == 200

        r2 = await ac.post("/api/v1/auth/refresh")
        assert r2.status_code == 401


async def test_config_exposes_auth_mode(client_factory) -> None:
    async with client_factory(_settings(auth_mode="single_user")) as ac:
        r = await ac.get("/api/v1/config")
        assert r.status_code == 200
        assert r.json()["data"]["auth_mode"] == "single_user"


async def test_login_rate_limited(client_factory) -> None:
    # Лимитер в тестах выключен глобально (conftest); включаем точечно
    # уже ПОСЛЕ создания app (create_app сбрасывает enabled из настроек).
    # Лимит берётся из реальных настроек — дефолт 10/minute.
    from app.core.rate_limit import limiter

    async with client_factory(_settings()) as ac:
        limiter.enabled = True
        limiter.reset()
        try:
            codes = []
            for _ in range(12):
                r = await ac.post(
                    "/api/v1/auth/login",
                    json={"email": "x@y.com", "password": "whatever-123"},
                )
                codes.append(r.status_code)
            # Первые 10 проходят (401 на неверный логин), дальше — 429.
            assert codes[-1] == 429
            assert 401 in codes
            last = await ac.post(
                "/api/v1/auth/login",
                json={"email": "x@y.com", "password": "whatever-123"},
            )
            assert last.json()["code"] == "RATE_LIMITED"
        finally:
            limiter.enabled = False
            limiter.reset()
