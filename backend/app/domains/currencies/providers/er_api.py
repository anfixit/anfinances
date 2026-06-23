"""Провайдер курсов валют через open.er-api.com.

Бесплатный, без ключа. Отдаёт курсы относительно base:
{"base_code": "RUB", "rates": {"USD": 0.0106, ...}}.
За Protocol, чтобы в тестах подменять без сети.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

import httpx

from app.config import Settings

__all__ = ["ErApiRatesProvider", "RatesProvider", "RatesProviderError"]

ClientFactory = Callable[[], httpx.AsyncClient]


class RatesProviderError(Exception):
    """Не удалось получить курсы у внешнего провайдера."""


class RatesProvider(Protocol):
    """Интерфейс источника курсов (для DI и тестов)."""

    async def fetch_rates(self, base: str) -> dict[str, Decimal]: ...


class ErApiRatesProvider:
    """Реализация поверх open.er-api.com."""

    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._url = settings.exchange_rate_api_url
        self._timeout = settings.exchange_rate_timeout_seconds
        self._client_factory = client_factory

    def _make_client(self) -> httpx.AsyncClient:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.AsyncClient(timeout=self._timeout)

    async def fetch_rates(self, base: str) -> dict[str, Decimal]:
        url = f"{self._url}/{base}"
        try:
            async with self._make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RatesProviderError(
                "Не удалось получить курсы валют."
            ) from exc

        if payload.get("result") == "error":
            raise RatesProviderError(
                payload.get("error-type", "unknown error")
            )

        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise RatesProviderError("Некорректный ответ провайдера.")

        return {
            str(code): Decimal(str(value)) for code, value in rates.items()
        }
