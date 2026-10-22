"""Общая обвязка тестов ИИ-интеграций.

Приложение на SQLite, юзер вставлен прямо в базу, JWT сайта
выпускается напрямую — регистрация с парольной политикой здесь
ни при чём.
"""

import base64
import hashlib
import json
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.core.models import Base
from app.core.security import create_access_token
from app.database import get_db
from app.domains.ai.clients import (
    ClientMetadataError,
    MetadataFetcher,
    clear_metadata_cache,
)
from app.domains.ai.ratelimit import connection_limiter
from app.domains.ai.routes import get_metadata_fetcher
from app.domains.auth.models import User
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL

API = "/api/v1"
RESOURCE = "https://anfinances.ru/mcp"
CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"


def make_settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "secret_key": "x" * 64,
        "auth_mode": "multi_user_no_verify",
        "hibp_enabled": False,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class FakeFetcher:
    """Документы клиентов (CIMD) из словаря, без сети."""

    def __init__(self, docs: dict[str, Any] | None = None) -> None:
        self.docs: dict[str, Any] = docs or {}
        self.calls: list[str] = []

    async def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if url not in self.docs:
            raise ClientMetadataError("Документ клиента ответил 404.")
        return json.dumps(self.docs[url]).encode()


@dataclass
class AiEnv:
    app: FastAPI
    client: AsyncClient
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: Settings
    user_id: uuid.UUID
    jwt: str

    @property
    def site(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.jwt}"}

    async def personal_token(self, scopes: list[str]) -> str:
        r = await self.client.post(
            f"{API}/ai/connections",
            json={"name": "Тест", "scopes": scopes},
            headers=self.site,
        )
        assert r.status_code == 201, r.text
        token: str = r.json()["data"]["token"]
        return token


@asynccontextmanager
async def ai_env(
    settings: Settings | None = None,
    fetcher: MetadataFetcher | None = None,
) -> AsyncIterator[AiEnv]:
    settings = settings or make_settings()
    kwargs: dict[str, Any] = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        kwargs = {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
    engine = create_async_engine(TEST_DATABASE_URL, **kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with maker() as session:
        user = User(
            email=f"ai-{uuid.uuid4()}@example.com", hashed_password="x"
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    app = create_app()

    async def _override_db() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_settings] = lambda: settings
    fake = fetcher or FakeFetcher()
    app.dependency_overrides[get_metadata_fetcher] = lambda: fake
    clear_metadata_cache()
    connection_limiter.reset()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        yield AiEnv(
            app=app,
            client=client,
            sessionmaker=maker,
            settings=settings,
            user_id=user_id,
            jwt=create_access_token(user_id, settings),
        )
    await engine.dispose()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge
