"""Интеграционные тесты /auth/* через httpx + SQLite in-memory."""

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
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
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
            base_url="http://test",
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
        tokens = r.json()["data"]
        assert tokens["access_token"]

        access = tokens["access_token"]
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
        r = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        refresh = r.json()["data"]["refresh_token"]

        r2 = await ac.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert r2.status_code == 200
        new_refresh = r2.json()["data"]["refresh_token"]
        assert new_refresh != refresh

        r3 = await ac.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert r3.status_code == 401


async def test_me_requires_auth(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        r = await ac.get("/api/v1/auth/me")
        assert r.status_code == 401


async def test_logout_invalidates_refresh(client_factory) -> None:
    async with client_factory(_settings()) as ac:
        r = await ac.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": STRONG},
        )
        refresh = r.json()["data"]["refresh_token"]
        await ac.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
        )
        r2 = await ac.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert r2.status_code == 401
