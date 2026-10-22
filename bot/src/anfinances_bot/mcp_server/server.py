"""MCP-сервер anfinances: Streamable HTTP на ``/mcp``.

Сервер без состояния на уровне протокола: каждый POST — отдельный
запрос, сессий MCP нет. Так его не ломают ни перезапуск контейнера
при деплое, ни балансировка — клиенту не нужно ничего
переустанавливать. Ответы обычным JSON, без потока событий:
инструменты отвечают одним куском, а поток только добавил бы
прокси поводов что-нибудь буферизовать.

Состояние, которое нужно между вызовами, — разбор выписки и ключи
повтора — живёт по подключению (``connection_id`` из whoami), а не
по токену: токен меняется при каждом обновлении, а разбор, показанный
пять минут назад, должен остаться.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import mcp_types as types
from anthropic.lib.tools import BetaAsyncFunctionTool
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route

from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.mcp_server.auth import (
    BackendUnavailableError,
    BearerGuard,
    Identity,
    TokenGate,
    bearer_token,
    challenge,
    protected_resource_metadata,
)
from anfinances_bot.mcp_server.catalog import (
    BY_NAME,
    CATALOG,
    IDEMPOTENCY_ARG,
    ToolSpec,
    bind,
    describe,
)
from anfinances_bot.mcp_server.client import (
    ForwardingClient,
    TokenRejectedError,
    acting_as,
    new_http_client,
)
from anfinances_bot.mcp_server.config import (
    WRITE_SCOPE,
    McpSettings,
    get_mcp_settings,
)
from anfinances_bot.mcp_server.toolbox import McpToolBox

logger = logging.getLogger("anfinances_bot.mcp")

__all__ = ["INSTRUCTIONS", "McpCore", "build_app"]

VERSION = "0.1.0"

# ChatGPT показывает первые 512 знаков как самостоятельный текст —
# главное должно уместиться в первый абзац.
INSTRUCTIONS = """\
anfinances — личные финансы: счета, операции, бюджет по конвертам \
(метод ВНБ), кредиты и цели. Инструменты работают с данными сайта \
anfinances.ru от имени этого подключения. Начинай с \
get_financial_overview. Запись доступна только с правом finance.write, \
и перед каждой записью клиент спрашивает подтверждение пользователя. \
Удалять и архивировать отсюда нельзя — только на сайте.

Суммы — положительные числа строкой («300», «1250.50»), знак ставит \
сайт. Даты — YYYY-MM-DD, месяцы — YYYY-MM. Категории — полные пути \
вида «Еда → Кофейни» из list_categories: новых не выдумывай. Если \
инструмент просит уточнить счёт — спроси пользователя, не угадывай.

Выписка из банка заносится в два шага: preview_statement разбирает и \
показывает, что будет занесено; список надо показать пользователю, и \
только после его согласия вызвать import_statement с preview_id из \
ответа. Повторные пишущие вызовы после обрыва связи делай с тем же \
idempotency_key — второй записи не будет.
"""

# Сколько помнить подключение без вызовов и ответы по ключу повтора.
_CONNECTION_TTL = 24 * 3600.0
_REPLAY_TTL = 24 * 3600.0


@dataclass
class _Replay:
    fingerprint: str
    result: types.CallToolResult
    expires: float


@dataclass
class _Connection:
    toolbox: McpToolBox
    tools: dict[str, BetaAsyncFunctionTool[Any]]
    seen: float
    # Пишущие вызовы одного подключения идут по очереди: так ключ
    # повтора не проскочит дважды, а разбор выписки не перепишется
    # посреди записи.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    replays: dict[str, _Replay] = field(default_factory=dict)


class McpCore:
    """Обработчики ``tools/list`` и ``tools/call``."""

    def __init__(
        self,
        settings: McpSettings,
        http: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self.gate = TokenGate(http, expected_resource=settings.mcp_public_url)
        self._client = ForwardingClient(http)
        self._connections: dict[str, _Connection] = {}
        self._creating = asyncio.Lock()
        # Описания одинаковы для всех подключений — считаем их один раз
        # на холостом наборе, без похода в сайт.
        idle = McpToolBox(
            self._client,
            default_accounts={},
            timezone=settings.mcp_timezone,
        )
        self._described = {spec.name: describe(idle, spec) for spec in CATALOG}

    # --- обработчики MCP ------------------------------------------

    async def list_tools(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        _, identity = await self._caller(ctx)
        return types.ListToolsResult(
            tools=[
                self._described[spec.name]
                for spec in CATALOG
                if _allowed(spec, identity)
            ]
        )

    async def call_tool(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        spec = BY_NAME.get(params.name)
        if spec is None:
            raise MCPError(
                code=types.INVALID_PARAMS,
                message=f"Unknown tool: {params.name}",
            )
        token, identity = await self._caller(ctx)
        if not _allowed(spec, identity):
            # Список инструментов этому токену запись не показывал, но
            # клиент может позвать её по имени из старого списка. До
            # сайта такой вызов не доходит.
            return _error(
                "У этого подключения нет права записи (finance.write). "
                "Переподключи anfinances с разрешением на запись.",
                challenge(
                    self._settings,
                    error="insufficient_scope",
                    description="finance.write is required",
                    scope=WRITE_SCOPE,
                ),
            )

        arguments = dict(params.arguments or {})
        key = (
            arguments.pop(IDEMPOTENCY_ARG, None) if spec.idempotency else None
        )
        with acting_as(token):
            connection = await self._connection(identity)
            if not spec.writes:
                return await self._run(connection, spec, arguments, token)
            async with connection.lock:
                if key is None:
                    return await self._run(connection, spec, arguments, token)
                return await self._run_once(
                    connection, spec, arguments, token, str(key)
                )

    # --- внутреннее -----------------------------------------------

    async def _caller(
        self, ctx: ServerRequestContext[Any, Any]
    ) -> tuple[str, Identity]:
        """Токен и подключение текущего HTTP-запроса.

        Проверку уже сделал ``BearerGuard``; здесь ответ берётся из
        памяти ``TokenGate``. Перепроверка — на случай, если запрос
        дошёл сюда в обход охраны: без токена инструмент не работает.
        """
        request = ctx.request
        token = (
            bearer_token(request.headers)
            if isinstance(request, Request)
            else None
        )
        if token is None:
            raise MCPError(code=types.INVALID_REQUEST, message="Unauthorized")
        try:
            identity = await self.gate.identify(token)
        except BackendUnavailableError as exc:
            raise MCPError(
                code=types.INTERNAL_ERROR,
                message="anfinances is temporarily unavailable",
            ) from exc
        if identity is None or not identity.can_read:
            raise MCPError(code=types.INVALID_REQUEST, message="Unauthorized")
        return token, identity

    async def _connection(self, identity: Identity) -> _Connection:
        now = self._clock()
        self._forget_idle(now)
        found = self._connections.get(identity.connection_id)
        if found is None:
            async with self._creating:
                found = self._connections.get(identity.connection_id)
                if found is None:
                    found = await self._open(identity, now)
                    self._connections[identity.connection_id] = found
        found.seen = now
        return found

    async def _open(self, identity: Identity, now: float) -> _Connection:
        """Набор инструментов для нового подключения.

        Часовой пояс и валюта — из профиля: «вчера вечером» должно
        значить её вечер, а не вечер по Гринвичу. Если сайт не отдаёт
        профиль этому токену, берём пояс из настроек.
        """
        timezone = self._settings.mcp_timezone
        home_currency: str | None = None
        try:
            profile = await self._client.me()
            ZoneInfo(profile.timezone)
            timezone = profile.timezone
            home_currency = profile.default_currency
        except (AnfinancesError, ValidationError, ZoneInfoNotFoundError):
            logger.info(
                "Профиль для подключения %s не прочитан, пояс %s",
                identity.connection_id,
                timezone,
            )
        toolbox = McpToolBox(
            self._client,
            default_accounts=self._settings.bot_default_accounts,
            timezone=timezone,
            home_currency=home_currency,
        )
        tools = {spec.name: bind(toolbox, spec) for spec in CATALOG}
        return _Connection(toolbox=toolbox, tools=tools, seen=now)

    def _forget_idle(self, now: float) -> None:
        stale = [
            cid
            for cid, conn in self._connections.items()
            if now - conn.seen > _CONNECTION_TTL
        ]
        for cid in stale:
            del self._connections[cid]

    async def _run_once(
        self,
        connection: _Connection,
        spec: ToolSpec,
        arguments: dict[str, Any],
        token: str,
        key: str,
    ) -> types.CallToolResult:
        """Выполнить запись не больше одного раза на ключ повтора.

        Клиент, не дождавшийся ответа, повторяет вызов — а запись
        уже прошла. С тем же ключом второй раз ничего не пишется,
        возвращается первый ответ. Тот же ключ с другими аргументами —
        это ошибка клиента, а не повтор: молча вернуть чужой ответ
        значило бы соврать, что записано новое.
        """
        now = self._clock()
        connection.replays = {
            k: r for k, r in connection.replays.items() if r.expires > now
        }
        slot = f"{spec.name}:{key}"
        fingerprint = _fingerprint(spec.name, arguments)
        previous = connection.replays.get(slot)
        if previous is not None:
            if previous.fingerprint != fingerprint:
                return _error(
                    f"{IDEMPOTENCY_ARG} «{key}» уже использован с другими "
                    "аргументами. Для новой записи нужен новый ключ."
                )
            return previous.result
        result = await self._run(connection, spec, arguments, token)
        if not result.is_error:
            connection.replays[slot] = _Replay(
                fingerprint, result, now + _REPLAY_TTL
            )
        return result

    async def _run(
        self,
        connection: _Connection,
        spec: ToolSpec,
        arguments: dict[str, Any],
        token: str,
    ) -> types.CallToolResult:
        tool = connection.tools[spec.name]
        try:
            text = await tool.call(arguments)
        except TokenRejectedError:
            self.gate.forget(token)
            return _error(
                "Токен больше не действует. Переподключи anfinances.",
                challenge(
                    self._settings,
                    error="invalid_token",
                    description="Token is invalid, expired or revoked",
                ),
            )
        except AnfinancesUnavailableError:
            logger.warning("Сайт не ответил на %s", spec.name, exc_info=True)
            return _error("Сайт anfinances не ответил. Повтори позже.")
        except AnfinancesError as exc:
            # Отказ сайта с текстом — модель по нему поправит вызов.
            return _error(f"Сайт отказал: {exc}")
        except ValueError as exc:
            return _error(_argument_problem(exc))
        except Exception:
            logger.exception("Инструмент %s упал", spec.name)
            return _error("Внутренняя ошибка инструмента.")
        return types.CallToolResult(
            content=[types.TextContent(text=str(text))]
        )


def _allowed(spec: ToolSpec, identity: Identity) -> bool:
    return identity.can_write if spec.writes else identity.can_read


def _error(
    text: str, www_authenticate: str | None = None
) -> types.CallToolResult:
    """Ошибка инструмента — результатом, чтобы модель её прочла.

    ``mcp/www_authenticate`` в ``_meta`` — сигнал ChatGPT, что нужно
    переподключиться с другими правами.
    """
    meta = (
        {"mcp/www_authenticate": [www_authenticate]}
        if www_authenticate is not None
        else None
    )
    return types.CallToolResult(
        content=[types.TextContent(text=text)], is_error=True, _meta=meta
    )


def _argument_problem(exc: ValueError) -> str:
    """Понятный текст про неверные аргументы.

    Обёртка инструмента прячет подробности в причину исключения —
    достаём их, иначе модели не по чему исправлять вызов.
    """
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'аргументы'}: "
            f"{err['msg']}"
            for err in cause.errors(include_url=False)
        )
        return f"Неверные аргументы: {problems}"
    return str(exc)


def _fingerprint(name: str, arguments: dict[str, Any]) -> str:
    raw = json.dumps(
        [name, arguments], sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _transport_security(settings: McpSettings) -> TransportSecuritySettings:
    """Проверка Host и Origin от подмены DNS.

    Host снаружи — домен сайта (Caddy его не переписывает), внутри
    compose — имя сервиса, на машине разработчика — localhost.
    """
    port = settings.mcp_port
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            settings.public_host,
            "mcp",
            f"mcp:{port}",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ],
        allowed_origins=list(settings.mcp_allowed_origins),
    )


def build_app(
    settings: McpSettings | None = None,
    http: httpx.AsyncClient | None = None,
) -> Starlette:
    """ASGI-приложение: ``/mcp`` под охраной и метаданные ресурса."""
    settings = settings or get_mcp_settings()
    owns_http = http is None
    backend = http or new_http_client(settings.anfinances_base_url)
    core = McpCore(settings, backend)
    server: Server[Any] = Server(
        "anfinances",
        version=VERSION,
        title="anfinances",
        instructions=INSTRUCTIONS,
        website_url=settings.mcp_issuer,
        on_list_tools=core.list_tools,
        on_call_tool=core.call_tool,
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=True,
        security_settings=_transport_security(settings),
    )
    metadata = protected_resource_metadata(settings)
    metadata_path = urlsplit(settings.resource_metadata_url).path

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            try:
                yield
            finally:
                if owns_http:
                    await backend.aclose()

    return Starlette(
        routes=[
            Route(
                urlsplit(settings.mcp_public_url).path or "/mcp",
                endpoint=BearerGuard(
                    manager.handle_request, core.gate, settings
                ),
            ),
            # Оба адреса: RFC 9728 вставляет путь ресурса после
            # well-known, а часть клиентов спрашивает корневой.
            Route(metadata_path, metadata, methods=["GET", "OPTIONS"]),
            Route(
                "/.well-known/oauth-protected-resource",
                metadata,
                methods=["GET", "OPTIONS"],
            ),
        ],
        lifespan=lifespan,
    )
