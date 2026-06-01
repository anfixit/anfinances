"""Pytest-фикстуры.

Заготовка. Полноценные фикстуры (test_db, client) добавим когда появятся
домены с реальной логикой для тестирования.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async-клиент для интеграционных тестов FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
