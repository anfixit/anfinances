"""Кто пришёл и с какими правами.

Токены выдаёт и проверяет сайт; MCP-сервер своих токенов не
держит и подписей не проверяет. Каждый запрос к ``/mcp`` он
показывает сайту через ``/ai/whoami`` и узнаёт, чьё это
подключение и какие у него права. Ответ помнится полминуты:
клиент шлёт по запросу на каждый вызов инструмента, и без памяти
сайт проверял бы один и тот же токен десятки раз за разговор.

Цена памяти — отозванный токен работает ещё до тридцати секунд.
Это допустимо: каждый запрос в сайт всё равно идёт с тем же
токеном, и сайт проверяет его сам.

Сам токен нигде не хранится и не пишется в лог — ключ памяти его
SHA-256.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from anfinances_bot.mcp_server.config import (
    READ_SCOPE,
    WRITE_SCOPE,
    McpSettings,
)

logger = logging.getLogger("anfinances_bot.mcp.auth")

__all__ = [
    "BackendUnavailableError",
    "BearerGuard",
    "Identity",
    "TokenGate",
    "bearer_token",
    "challenge",
    "protected_resource_metadata",
]

# Сколько помнить ответ whoami — и «да», и «нет».
CACHE_SECONDS = 30.0
# Предохранитель памяти: перебор случайных токенов не должен раздуть
# словарь до бесконечности.
_MAX_CACHED = 1000


@dataclass(frozen=True)
class Identity:
    """Ответ сайта на whoami: чьё подключение и что ему можно."""

    connection_id: str
    user_id: str
    scopes: frozenset[str]
    kind: str
    name: str

    @property
    def can_read(self) -> bool:
        return READ_SCOPE in self.scopes or WRITE_SCOPE in self.scopes

    @property
    def can_write(self) -> bool:
        return WRITE_SCOPE in self.scopes


class BackendUnavailableError(RuntimeError):
    """Сайт не ответил на whoami — это не повод считать токен плохим."""


def bearer_token(headers: Headers) -> str | None:
    """Токен из ``Authorization: Bearer …`` или None."""
    value = headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.casefold() != "bearer":
        return None
    token = token.strip()
    return token or None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenGate:
    """Проверка токена через сайт с памятью на полминуты."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        expected_resource: str | None = None,
        ttl: float = CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._expected_resource = expected_resource
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[str, tuple[float, Identity | None]] = {}

    async def identify(self, token: str) -> Identity | None:
        """Подключение по токену; None — токен не принят."""
        key = _digest(token)
        now = self._clock()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        identity = await self._ask(token)
        if len(self._cache) >= _MAX_CACHED:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            if len(self._cache) >= _MAX_CACHED:
                self._cache.clear()
        self._cache[key] = (now + self._ttl, identity)
        return identity

    def forget(self, token: str) -> None:
        """Сайт отказал токену посреди работы — не верить памяти."""
        self._cache.pop(_digest(token), None)

    async def _ask(self, token: str) -> Identity | None:
        try:
            response = await self._http.get(
                "/ai/whoami", headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError as exc:
            raise BackendUnavailableError(str(exc)) from exc
        if response.status_code >= 500:
            raise BackendUnavailableError(f"whoami → {response.status_code}")
        if response.status_code != 200:
            return None
        try:
            data = response.json()["data"]
            identity = Identity(
                connection_id=str(data["connection_id"]),
                user_id=str(data["user_id"]),
                scopes=frozenset(str(s) for s in data["scopes"]),
                kind=str(data.get("kind") or ""),
                name=str(data.get("name") or ""),
            )
        except (ValueError, KeyError, TypeError):
            logger.warning("whoami вернул неожиданный ответ")
            return None
        if not self._issued_for_us(data):
            logger.warning(
                "Токен подключения %s выписан не для этого сервера",
                identity.connection_id,
            )
            return None
        return identity

    def _issued_for_us(self, data: dict[str, Any]) -> bool:
        """Сверить ресурс токена, если сайт его сообщает.

        Спецификация MCP требует принимать только токены, выписанные
        для этого сервера. Личный токен ресурса не имеет — он для
        любого клиента владелицы, и его пропускаем.
        """
        resource = data.get("resource")
        if not resource or self._expected_resource is None:
            return True
        return str(resource).rstrip("/") == self._expected_resource


# Какие права просить при входе. Клиент запрашивает ровно то, что
# названо в заголовке: с одним finance.read ChatGPT попросил только
# чтение, и галочки «Записывать» на экране согласия просто не было.
# Просим оба — а что выдать, решает человек: запись там выключена
# по умолчанию.
LOGIN_SCOPES = f"{READ_SCOPE} {WRITE_SCOPE}"


def challenge(
    settings: McpSettings,
    *,
    error: str | None = None,
    description: str | None = None,
    scope: str = LOGIN_SCOPES,
) -> str:
    """Значение ``WWW-Authenticate`` по RFC 6750 и RFC 9728.

    Тексты только латиницей: заголовок HTTP — latin-1, и кириллица
    в нём роняет ответ целиком.
    """
    parts = [f'resource_metadata="{settings.resource_metadata_url}"']
    parts.append(f'scope="{scope}"')
    if error is not None:
        parts.insert(0, f'error="{error}"')
        if description is not None:
            parts.insert(1, f'error_description="{description}"')
    return "Bearer " + ", ".join(parts)


class BearerGuard:
    """ASGI-обёртка над ``/mcp``: без годного токена дальше не пустит.

    Ответ 401 с ``WWW-Authenticate`` — то, с чего ChatGPT и Claude
    начинают вход: из заголовка они узнают адрес метаданных, а из
    метаданных — сервер авторизации.
    """

    def __init__(
        self, app: ASGIApp, gate: TokenGate, settings: McpSettings
    ) -> None:
        self._app = app
        self._gate = gate
        self._settings = settings

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        response = await self._check(Headers(scope=scope))
        if response is not None:
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    async def _check(self, headers: Headers) -> Response | None:
        token = bearer_token(headers)
        if token is None:
            # Без токена — без кода ошибки: так велит RFC 6750, и
            # клиенты по этому отличают «войди» от «войди заново».
            return _deny(401, challenge(self._settings), "Нужен токен.")
        try:
            identity = await self._gate.identify(token)
        except BackendUnavailableError:
            logger.warning("Сайт не ответил на whoami", exc_info=True)
            # Не 401: иначе клиент выбросит исправный токен и
            # погонит человека заново через вход из-за сбоя сайта.
            return JSONResponse(
                {"error": "temporarily_unavailable"},
                status_code=503,
                headers={"Retry-After": "5"},
            )
        if identity is None:
            return _deny(
                401,
                challenge(
                    self._settings,
                    error="invalid_token",
                    description="Token is invalid, expired or revoked",
                ),
                "Токен не принят.",
            )
        if not identity.can_read:
            return _deny(
                403,
                challenge(
                    self._settings,
                    error="insufficient_scope",
                    description="finance.read is required",
                    scope=READ_SCOPE,
                ),
                "У токена нет права читать финансы.",
            )
        return None


def _deny(status: int, header: str, message: str) -> Response:
    return JSONResponse(
        {"error": "unauthorized", "message": message},
        status_code=status,
        headers={"WWW-Authenticate": header},
    )


def protected_resource_metadata(
    settings: McpSettings,
) -> Callable[[Request], Any]:
    """Обработчик метаданных защищённого ресурса (RFC 9728).

    JSON собирается строками, а не моделью с URL: pydantic дописал бы
    к ``https://anfinances.ru`` слэш, а издателя клиенты сверяют
    строкой с метаданными сервера авторизации.
    """
    body = {
        "resource": settings.mcp_public_url,
        "authorization_servers": [settings.mcp_issuer],
        "scopes_supported": [READ_SCOPE, WRITE_SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "anfinances",
    }
    # Документ публичный; разрешаем чтение из браузера, чтобы
    # отладочные клиенты вроде MCP Inspector тоже его видели.
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    async def endpoint(request: Request) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=cors)
        return JSONResponse(
            body, headers={**cors, "Cache-Control": "max-age=3600"}
        )

    return endpoint
