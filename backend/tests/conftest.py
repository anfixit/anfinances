"""Pytest-фикстуры.

Тестовые переменные окружения выставляются ДО импорта app.*:
app.main на уровне модуля вызывает create_app() → get_settings(),
поэтому без secret_key падал бы сам сбор тестов. Так тесты не
зависят от .env.
"""

import os

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

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncClient:
    """Async-клиент для интеграционных тестов FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
