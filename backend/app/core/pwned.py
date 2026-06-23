"""Проверка пароля по базе утечек HIBP (k-anonymity).

В сеть уходят только первые 5 символов SHA-1 хеша пароля —
сам пароль и его полный хеш не передаются. HIBP возвращает все
суффиксы с этим префиксом, совпадение ищется локально.

Поведение при сетевой ошибке управляется hibp_fail_open:
True  — пропустить проверку (self-host без стабильной сети);
False — отказать (строгий режим для публичного SaaS).
"""

import hashlib
from collections.abc import Callable
from typing import Protocol

import httpx

from app.config import Settings

__all__ = ["HibpChecker", "PwnedChecker", "PwnedError"]

_API_URL = "https://api.pwnedpasswords.com/range/"

ClientFactory = Callable[[], httpx.AsyncClient]


class PwnedError(Exception):
    """Пароль найден в базе утечек."""


class PwnedChecker(Protocol):
    """Интерфейс проверки на компрометацию (для подмены в тестах)."""

    async def assert_not_pwned(self, plain: str) -> None: ...


class HibpChecker:
    """Боевая реализация через api.pwnedpasswords.com.

    client_factory внедряется для тестов: туда передаётся
    AsyncClient с MockTransport вместо реальной сети.
    """

    def __init__(
        self,
        settings: Settings,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._enabled = settings.hibp_enabled
        self._fail_open = settings.hibp_fail_open
        self._timeout = settings.hibp_timeout_seconds
        self._client_factory = client_factory or self._default_factory

    def _default_factory(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout)

    async def assert_not_pwned(self, plain: str) -> None:
        if not self._enabled:
            return

        # HIBP range API работает по SHA-1 (k-anonymity): шлём первые
        # 5 символов хэша, сверяем суффикс. Это не хранение пароля —
        # SHA-1 здесь обязателен протоколом, не выбор криптостойкости.
        digest = hashlib.sha1(  # noqa: S324
            plain.encode("utf-8")
        ).hexdigest()
        prefix, suffix = digest[:5].upper(), digest[5:].upper()

        try:
            async with self._client_factory() as client:
                resp = await client.get(f"{_API_URL}{prefix}")
                resp.raise_for_status()
                body = resp.text
        except httpx.HTTPError:
            if self._fail_open:
                return
            raise PwnedError(
                "Не удалось проверить пароль по базе утечек."
            ) from None

        for line in body.splitlines():
            found_suffix, _, _count = line.partition(":")
            if found_suffix.strip().upper() == suffix:
                raise PwnedError(
                    "Этот пароль найден в утечках данных. Выберите другой."
                )
