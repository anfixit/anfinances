"""Async SQLAlchemy: engine, session factory и базовый класс моделей.

Модели данных будут добавлены в шаге 2. Сейчас здесь только инфраструктура.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей.

    Все модели в app/domains/*/models.py наследуются от него.
    Alembic использует Base.metadata для автогенерации миграций.
    """


# Engine создаётся один раз на процесс. Импорт этого модуля = создание engine.
# Если нужно лениво — можно завернуть в функцию, но для FastAPI это норм.
_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    str(_settings.database_url),
    echo=_settings.db_echo,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    # проверяет соединение перед использованием
    pool_pre_ping=True,
)

# expire_on_commit=False — после commit() объекты остаются юзабельными.
# Это важно для FastAPI: после commit мы часто возвращаем объект в response.
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI-зависимость: даёт сессию БД на время request.

    Использование:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...

    Сессия закрывается автоматически. Commit делает сервис, не зависимость.
    """
    async with AsyncSessionLocal() as session:
        yield session
