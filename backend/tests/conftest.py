"""Pytest-фикстуры.

Тестовые переменные окружения выставляются ДО импорта app.*:
app.database на уровне модуля вызывает get_settings(), поэтому без
secret_key падал бы сам сбор тестов. Так тесты не зависят от .env.
"""

import os

os.environ.setdefault("SECRET_KEY", "0" * 64)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "false")

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
