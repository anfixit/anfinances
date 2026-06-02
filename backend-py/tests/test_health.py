"""Smoke-тест: health-эндпоинт отвечает.

Тест /health/live не требует БД и работает без compose.
Тест /health/ready пропускаем, если БД недоступна.
"""

import pytest
from httpx import AsyncClient


async def test_health_live(client: AsyncClient) -> None:
    """Liveness-эндпоинт всегда отвечает 200 OK."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.skip(
    reason="Требует поднятой БД — запускается в integration suite"
)
async def test_health_ready(client: AsyncClient) -> None:
    """Readiness-эндпоинт проверяет БД."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
