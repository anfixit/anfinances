"""Тесты bootstrap_single_user на SQLite in-memory."""

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.core.models import Base
from app.domains.auth.bootstrap import bootstrap_single_user
from app.domains.auth.models import User

PW = "fluffy-zebra-canyon-marble-97"


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {"secret_key": "x" * 64}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with maker() as s:
        yield s
    await engine.dispose()


async def _count_users(session: AsyncSession) -> int:
    result = await session.execute(select(User))
    return len(result.scalars().all())


async def test_creates_user(session: AsyncSession) -> None:
    s = _settings(
        auth_mode="single_user",
        single_user_email="me@home.lan",
        single_user_password=PW,
    )
    await bootstrap_single_user(session, s)
    assert await _count_users(session) == 1


async def test_idempotent(session: AsyncSession) -> None:
    s = _settings(
        auth_mode="single_user",
        single_user_email="me@home.lan",
        single_user_password=PW,
    )
    await bootstrap_single_user(session, s)
    await bootstrap_single_user(session, s)
    assert await _count_users(session) == 1


async def test_skips_without_email(session: AsyncSession) -> None:
    s = _settings(auth_mode="single_user", single_user_password=PW)
    await bootstrap_single_user(session, s)
    assert await _count_users(session) == 0


async def test_skips_in_multi_user(session: AsyncSession) -> None:
    s = _settings(
        auth_mode="multi_user_no_verify",
        single_user_email="me@home.lan",
        single_user_password=PW,
    )
    await bootstrap_single_user(session, s)
    assert await _count_users(session) == 0
