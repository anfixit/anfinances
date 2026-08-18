"""HTTP-клиент к anfinances.

Бот — обычный потребитель публичного API: входит теми же учётными
данными единственного пользователя и доступа к базе не имеет.
Access-токен живёт 15 минут, поэтому по первой 401 клиент молча
перелогинивается и повторяет запрос ровно один раз — не в цикле.
"""

import logging
from typing import Any

import httpx

from anfinances_bot.anfinances.schemas import (
    AccountRead,
    CategoryRead,
    UserProfile,
)
from anfinances_bot.config import BotSettings

logger = logging.getLogger("anfinances_bot.client")

__all__ = ["AnfinancesClient", "AnfinancesError", "AnfinancesUnavailableError"]


class AnfinancesError(RuntimeError):
    """Ошибка обращения к anfinances."""


class AnfinancesUnavailableError(AnfinancesError):
    """Сайт недоступен: сеть, таймаут или 5xx."""


class AnfinancesClient:
    def __init__(self, settings: BotSettings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._http = httpx.AsyncClient(
            base_url=settings.anfinances_base_url,
            # Сервер слабый, и справочники отвечают за секунду с
            # лишним. Пятнадцати секунд не хватало, когда
            # приходило несколько файлов сразу.
            timeout=httpx.Timeout(60.0),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def login(self) -> None:
        payload = {
            "email": self._settings.single_user_email,
            "password": (
                self._settings.single_user_password.get_secret_value()
            ),
        }
        try:
            response = await self._http.post("/auth/login", json=payload)
        except httpx.HTTPError as exc:
            raise AnfinancesUnavailableError(str(exc)) from exc

        if response.status_code >= 500:
            raise AnfinancesUnavailableError(f"login {response.status_code}")
        if response.status_code != 200:
            raise AnfinancesError(
                "Не удалось войти в anfinances: проверьте "
                "SINGLE_USER_EMAIL и SINGLE_USER_PASSWORD."
            )
        self._token = response.json()["data"]["access_token"]

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Выполнить запрос; по 401 перелогиниться и повторить один раз."""
        if self._token is None:
            await self.login()

        response = await self._send(method, path, **kwargs)
        if response.status_code == 401:
            await self.login()
            response = await self._send(method, path, **kwargs)

        if response.status_code >= 500:
            raise AnfinancesUnavailableError(
                f"{method} {path} → {response.status_code}"
            )
        if response.status_code >= 400:
            raise AnfinancesError(_error_text(response))
        if response.status_code == 204 or not response.content:
            return None
        return response.json().get("data")

    async def _send(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            return await self._http.request(
                method, path, headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise AnfinancesUnavailableError(str(exc)) from exc

    async def me(self) -> UserProfile:
        return UserProfile.model_validate(
            await self.request("GET", "/auth/me")
        )

    async def accounts(self) -> list[AccountRead]:
        rows = await self.request("GET", "/accounts")
        return [AccountRead.model_validate(row) for row in rows]

    async def categories(self) -> list[CategoryRead]:
        rows = await self.request("GET", "/categories")
        return [CategoryRead.model_validate(row) for row in rows]


def _error_text(response: httpx.Response) -> str:
    """Достать человеческий текст ошибки из ответа API."""
    try:
        body = response.json()
    except ValueError:
        return f"Ошибка {response.status_code}"
    if not isinstance(body, dict):
        return f"Ошибка {response.status_code}"
    for key in ("detail", "message", "error"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return f"Ошибка {response.status_code}"
