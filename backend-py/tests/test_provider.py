"""Тесты ErApiRatesProvider (без сети, MockTransport)."""

from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.domains.currencies.providers.er_api import (
    ErApiRatesProvider,
    RatesProviderError,
)


def _settings() -> Settings:
    return Settings(secret_key="x" * 64)  # type: ignore[call-arg]


def _provider(transport: httpx.MockTransport) -> ErApiRatesProvider:
    return ErApiRatesProvider(
        _settings(),
        client_factory=lambda: httpx.AsyncClient(
            transport=transport, timeout=1.0
        ),
    )


async def test_fetch_ok() -> None:
    body = {
        "result": "success",
        "base_code": "RUB",
        "rates": {"USD": 0.0106, "EUR": 0.0098},
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    rates = await _provider(transport).fetch_rates("RUB")
    assert rates["USD"] == Decimal("0.0106")
    assert rates["EUR"] == Decimal("0.0098")


async def test_fetch_api_error() -> None:
    body = {"result": "error", "error-type": "unsupported-code"}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
    with pytest.raises(RatesProviderError):
        await _provider(transport).fetch_rates("RUB")


async def test_fetch_http_error() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(boom)
    with pytest.raises(RatesProviderError):
        await _provider(transport).fetch_rates("RUB")


async def test_fetch_malformed() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"result": "success"})
    )
    with pytest.raises(RatesProviderError):
        await _provider(transport).fetch_rates("RUB")
