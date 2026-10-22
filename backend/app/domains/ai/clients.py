"""Кто такой OAuth-клиент и куда ему можно вернуть код.

Клиент узнаётся тремя путями, по порядку:

1. Заранее заведённый в настройках (AI_PREDEFINED_CLIENTS).
2. client_id — https-адрес документа метаданных (CIMD). Документ
   скачивается, но только с хостов из AI_CLIENT_HOSTS: иначе любой
   мог бы заставить сервер ходить по произвольным адресам.
3. Зарегистрированный динамически (RFC 7591) — ищется в базе.

Адрес возврата сверяется со списком клиента побайтно: любая
«нормализация» здесь — это открытый редирект.
"""

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import Settings
from app.domains.ai.repository import AiRepository

__all__ = [
    "ClientInfo",
    "ClientMetadataError",
    "clean_client_name",
    "HttpxMetadataFetcher",
    "MetadataFetcher",
    "UnknownClientError",
    "clear_metadata_cache",
    "host_of",
    "is_allowed_dcr_redirect",
    "is_safe_redirect_uri",
    "resolve_client",
]

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Документ клиента — пара сотен байт. Ограничение защищает от
# попытки скормить серверу гигабайт.
_MAX_METADATA_BYTES = 64 * 1024
_MAX_REDIRECTS = 2
_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_ENTRIES = 64
_MAX_CLIENT_NAME = 100


@dataclass(frozen=True, slots=True)
class ClientInfo:
    client_id: str
    name: str
    redirect_uris: tuple[str, ...]


class UnknownClientError(Exception):
    """Клиента нет или его не удалось проверить.

    Сообщение показывается пользователю на странице согласия.
    """


class ClientMetadataError(Exception):
    """Документ метаданных клиента не скачался или кривой."""


class MetadataFetcher(Protocol):
    async def fetch(self, url: str) -> bytes: ...


def host_of(uri: str) -> str:
    return (urlsplit(uri).hostname or "").lower()


def is_safe_redirect_uri(uri: str) -> bool:
    """Годится ли адрес как redirect_uri вообще, без учёта клиента.

    https — да; http — только на свою машину (localhost, 127.0.0.1),
    куда уходит код у Claude Code. Фрагмент и логин в адресе
    запрещены (OAuth 2.1, §2.3.1): за ними прячут подмену хоста.
    """
    if len(uri) > 2000:
        return False
    try:
        parts = urlsplit(uri)
        _ = parts.port  # бросает ValueError на кривом порте
    except ValueError:
        return False
    if parts.fragment or "#" in uri or "@" in parts.netloc:
        return False
    host = (parts.hostname or "").lower()
    if not host:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and host in _LOOPBACK_HOSTS


def is_allowed_dcr_redirect(uri: str, settings: Settings) -> bool:
    """Можно ли зарегистрировать такой адрес возврата через DCR."""
    if not is_safe_redirect_uri(uri):
        return False
    parts = urlsplit(uri)
    host = (parts.hostname or "").lower()
    if parts.scheme == "http":
        return host in _LOOPBACK_HOSTS
    allowed = {h.lower() for h in settings.ai_redirect_hosts}
    return host in allowed and parts.port is None


def clean_client_name(raw: object, fallback: str) -> str:
    if not isinstance(raw, str):
        return fallback
    # Управляющие символы в имени клиента — способ подделать текст
    # на странице согласия.
    name = "".join(ch for ch in raw if ch.isprintable()).strip()
    return name[:_MAX_CLIENT_NAME] or fallback


class HttpxMetadataFetcher:
    """Скачивает документ метаданных клиента по https.

    Редиректы — только в пределах того же хоста и по https: иначе
    проверка хоста из списка разрешённых теряет смысл.
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = settings.ai_client_metadata_timeout_seconds
        # Подмена транспорта — для тестов, в сеть они не ходят.
        self._transport = transport

    async def fetch(self, url: str) -> bytes:
        origin_host = host_of(url)
        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            current = url
            for _ in range(_MAX_REDIRECTS + 1):
                body, location = await self._get(client, current)
                if location is None:
                    return body
                nxt = urljoin(current, location)
                parts = urlsplit(nxt)
                if parts.scheme != "https" or host_of(nxt) != origin_host:
                    raise ClientMetadataError(
                        "Документ клиента перенаправляет на чужой хост."
                    )
                current = nxt
        raise ClientMetadataError("Слишком много перенаправлений.")

    async def _get(
        self, client: httpx.AsyncClient, url: str
    ) -> tuple[bytes, str | None]:
        try:
            async with client.stream(
                "GET", url, headers={"Accept": "application/json"}
            ) as resp:
                if resp.is_redirect:
                    return b"", resp.headers.get("location")
                if resp.status_code != 200:
                    raise ClientMetadataError(
                        f"Документ клиента ответил {resp.status_code}."
                    )
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > _MAX_METADATA_BYTES:
                        raise ClientMetadataError(
                            "Документ клиента слишком большой."
                        )
                    chunks.append(chunk)
                return b"".join(chunks), None
        except httpx.HTTPError as exc:
            raise ClientMetadataError(
                "Не удалось скачать документ клиента."
            ) from exc


# client_id → (момент протухания, клиент). Документ меняется редко,
# а авторизация дёргает его дважды подряд (проверка и одобрение).
_metadata_cache: dict[str, tuple[float, ClientInfo]] = {}


def clear_metadata_cache() -> None:
    _metadata_cache.clear()


def _is_metadata_url(client_id: str) -> bool:
    return client_id.startswith("https://")


def _check_metadata_url(client_id: str, settings: Settings) -> None:
    try:
        parts = urlsplit(client_id)
        port = parts.port
    except ValueError as exc:
        raise UnknownClientError("Некорректный адрес клиента.") from exc
    host = (parts.hostname or "").lower()
    allowed = {h.lower() for h in settings.ai_client_hosts}
    if (
        parts.fragment
        or "@" in parts.netloc
        or port is not None
        or parts.path in ("", "/")
        or host not in allowed
    ):
        raise UnknownClientError(
            f"Клиент с адреса {host or client_id} не входит в список "
            "разрешённых."
        )


def _parse_metadata(client_id: str, body: bytes) -> ClientInfo:
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ClientMetadataError("Документ клиента — не JSON.") from exc
    if not isinstance(doc, dict):
        raise ClientMetadataError("Документ клиента — не объект.")
    # По CIMD client_id в документе обязан совпадать с адресом,
    # с которого его скачали: иначе документ чужой.
    if doc.get("client_id") != client_id:
        raise ClientMetadataError("client_id в документе не совпадает.")
    uris = doc.get("redirect_uris")
    if (
        not isinstance(uris, list)
        or not uris
        or not all(isinstance(u, str) for u in uris)
    ):
        raise ClientMetadataError("В документе клиента нет redirect_uris.")
    return ClientInfo(
        client_id=client_id,
        name=clean_client_name(doc.get("client_name"), host_of(client_id)),
        redirect_uris=tuple(uris),
    )


async def _resolve_metadata_client(
    client_id: str, settings: Settings, fetcher: MetadataFetcher
) -> ClientInfo:
    _check_metadata_url(client_id, settings)
    now = time.monotonic()
    cached = _metadata_cache.get(client_id)
    if cached is not None and cached[0] > now:
        return cached[1]
    try:
        info = _parse_metadata(client_id, await fetcher.fetch(client_id))
    except ClientMetadataError as exc:
        raise UnknownClientError(str(exc)) from exc
    if len(_metadata_cache) >= _CACHE_MAX_ENTRIES:
        _metadata_cache.clear()
    _metadata_cache[client_id] = (now + _CACHE_TTL_SECONDS, info)
    return info


def _predefined(client_id: str, settings: Settings) -> ClientInfo | None:
    for client in settings.ai_predefined_clients:
        if client.client_id == client_id:
            return ClientInfo(
                client_id=client.client_id,
                name=clean_client_name(client.name, client.client_id),
                redirect_uris=tuple(client.redirect_uris),
            )
    return None


async def resolve_client(
    client_id: str,
    settings: Settings,
    repo: AiRepository,
    fetcher: MetadataFetcher,
) -> ClientInfo:
    """Найти клиента по client_id или бросить UnknownClientError."""
    if len(client_id) > 2000:
        raise UnknownClientError("Слишком длинный client_id.")
    predefined = _predefined(client_id, settings)
    if predefined is not None:
        return predefined
    if _is_metadata_url(client_id):
        return await _resolve_metadata_client(client_id, settings, fetcher)
    if len(client_id) <= 64:
        stored = await repo.get_client(client_id)
        if stored is not None:
            uris: Sequence[object] = stored.redirect_uris
            return ClientInfo(
                client_id=stored.client_id,
                name=stored.client_name,
                redirect_uris=tuple(u for u in uris if isinstance(u, str)),
            )
    raise UnknownClientError("Неизвестный клиент.")
