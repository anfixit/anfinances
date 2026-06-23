"""Async SQLAlchemy: фабрики engine/session и зависимость get_db.

Engine НЕ создаётся на импорте (M4): его поднимает lifespan и кладёт
в app.state. get_db берёт sessionmaker оттуда. Так фабрика приложения
не завязана на доступность БД во время импорта, а тесты подменяют
get_db без побочного engine на постгрес.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.core.models import Base


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Собрать async engine из настроек."""
    return create_async_engine(
        str(settings.database_url),
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


def create_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Собрать session factory поверх engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    """FastAPI-зависимость: сессия БД из app.state на время request.

    Сессия закрывается автоматически. Commit делает сервис/роут.
    """
    sessionmaker: async_sessionmaker[AsyncSession] = (
        request.app.state.sessionmaker
    )
    async with sessionmaker() as session:
        yield session


__all__ = [
    "Base",
    "create_db_engine",
    "create_sessionmaker",
    "get_db",
]
