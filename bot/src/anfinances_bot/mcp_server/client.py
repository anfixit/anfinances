"""Клиент anfinances, который ходит с токеном вызывающего.

У бота клиент входит логином и паролем владелицы. Здесь так нельзя:
права у каждого подключения свои — одно только читает, другое ещё
и записывает, — и проверяет их сайт. Значит, в сайт должен уйти
ровно тот токен, с которым пришёл запрос, без подмены и без
«служебного» входа, который молча расширил бы права.

Токен берётся из контекстной переменной, а не хранится в объекте.
Набор инструментов живёт дольше одного запроса, и токен у
подключения меняется при каждом обновлении. Будь он полем клиента,
два одновременных запроса одного подключения подменяли бы токены
друг другу.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpx

from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
    _error_text,
)
from anfinances_bot.anfinances.schemas import (
    AccountRead,
    CategoryRead,
    UserProfile,
)

__all__ = [
    "ForwardingClient",
    "TokenRejectedError",
    "acting_as",
    "new_http_client",
]

_caller_token: ContextVar[str | None] = ContextVar(
    "anfinances_mcp_caller_token", default=None
)


class TokenRejectedError(AnfinancesError):
    """Сайт не принял токен: отозван или истёк после проверки."""


def new_http_client(base_url: str) -> httpx.AsyncClient:
    """Общий пул соединений к сайту на все подключения."""
    # Шестьдесят секунд — как у бота: сервер слабый, а справочники
    # и импорт выписки отвечают дольше, чем хотелось бы.
    return httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(60.0))


@contextmanager
def acting_as(token: str) -> Iterator[None]:
    """Выполнять запросы к сайту от имени этого токена."""
    reset = _caller_token.set(token)
    try:
        yield
    finally:
        _caller_token.reset(reset)


class ForwardingClient:
    """Реализует тот же протокол, что ждёт ``ToolBox`` у клиента."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = _caller_token.get()
        if token is None:
            # Запрос без токена — ошибка в коде сервера, а не повод
            # сходить в сайт анонимно.
            raise RuntimeError("Запрос к сайту вне acting_as().")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self._http.request(
                method, path, headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise AnfinancesUnavailableError(str(exc)) from exc

        if response.status_code == 401:
            # Перелогиниваться некем и нечем: токен чужой. Пусть
            # клиент обновит его сам.
            raise TokenRejectedError("Токен больше не действует.")
        if response.status_code >= 500:
            raise AnfinancesUnavailableError(
                f"{method} {path} → {response.status_code}"
            )
        if response.status_code >= 400:
            raise AnfinancesError(_error_text(response))
        if response.status_code == 204 or not response.content:
            return None
        return response.json().get("data")

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
