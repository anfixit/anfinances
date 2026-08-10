"""Pytest-фикстуры.

Тестовые переменные окружения выставляются ДО импорта app.*:
app.main на уровне модуля вызывает create_app() → get_settings(),
поэтому без secret_key падал бы сам сбор тестов. Так тесты не
зависят от .env.
"""

import os
import uuid

os.environ.setdefault("SECRET_KEY", "0" * 64)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# Профиль тестовой БД (M1): по умолчанию SQLite в памяти, но через
# TEST_DATABASE_URL можно прогнать интеграционные тесты на PostgreSQL
# (CI поднимает throwaway-инстанс) — ближе к проду.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.core.models import Base  # noqa: E402
from app.main import app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncClient:
    """Async-клиент для интеграционных тестов FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncSession:
    """Сессия на чистой схеме; после теста всё откатывается.

    Для SQLite в памяти нужен StaticPool: иначе каждое соединение
    получает собственную пустую базу и созданной схемы не видит.
    """
    kwargs: dict[str, object] = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        kwargs = {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        }
    engine = create_async_engine(TEST_DATABASE_URL, **kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def ledger(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    """Юзер, валюты и два счёта — минимум для вставки операции.

    На PostgreSQL внешние ключи обязательны, на SQLite по умолчанию
    нет. Готовим настоящие родительские строки, чтобы тесты вели себя
    одинаково на обоих профилях.
    """
    from app.core.enums import AccountType  # noqa: PLC0415
    from app.domains.accounts.models import Account  # noqa: PLC0415
    from app.domains.auth.models import User  # noqa: PLC0415
    from app.domains.currencies.models import Currency  # noqa: PLC0415

    existing = await db_session.execute(select(Currency.code))
    known = set(existing.scalars().all())
    for code, name in (("RUB", "Рубль"), ("UZS", "Сум")):
        if code not in known:
            db_session.add(Currency(code=code, name=name, decimals=2))

    user = User(
        email=f"test-{uuid.uuid4()}@example.com",
        hashed_password="x",
    )
    db_session.add(user)
    await db_session.flush()

    rub = Account(
        user_id=user.id,
        name="Альфа",
        type=AccountType.CARD,
        currency_code="RUB",
    )
    uzs = Account(
        user_id=user.id,
        name="Наличные сумы",
        type=AccountType.CASH,
        currency_code="UZS",
    )
    db_session.add_all([rub, uzs])
    await db_session.flush()

    return {"user": user.id, "rub": rub.id, "uzs": uzs.id}
