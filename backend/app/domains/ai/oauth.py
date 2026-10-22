"""OAuth 2.1 сервер авторизации для ИИ-ассистентов.

Поток: ассистент открывает у пользователя страницу согласия
(SPA, /oauth/authorize), та спрашивает бэкенд, корректен ли запрос,
и после «Разрешить» получает адрес возврата с кодом. Ассистент
меняет код на пару токенов с PKCE.

Что здесь принципиально:

* PKCE S256 обязателен — у публичных клиентов нет секрета, и
  перехваченный код без verifier бесполезен.
* Код одноразовый и привязан ко всему, что одобрил пользователь.
  Повторное предъявление — признак перехвата: подключение,
  выданное по этому коду, отзывается.
* Refresh ротируется на каждом обмене; старый, предъявленный снова,
  отзывает всё подключение (OAuth 2.1, §4.3.1).
* В каждый ответ авторизации, включая ошибки, кладётся ``iss``
  (RFC 9207) — защита от подмены сервера (mix-up).

error_description по RFC 6749 — только ASCII, поэтому для протокола
описания английские; пользователю на странице согласия показывается
русское ``message``.
"""

import re
import secrets
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.config import Settings
from app.domains.ai.clients import (
    ClientInfo,
    MetadataFetcher,
    UnknownClientError,
    clean_client_name,
    host_of,
    is_allowed_dcr_redirect,
    is_safe_redirect_uri,
    redirect_matches,
    resolve_client,
)
from app.domains.ai.models import (
    CONNECTION_OAUTH,
    TOKEN_ACCESS,
    TOKEN_REFRESH,
    AiAuthCode,
    AiConnection,
    AiOAuthClient,
    AiToken,
)
from app.domains.ai.repository import AiRepository
from app.domains.ai.scopes import (
    ALL_SCOPES,
    InvalidScopeError,
    join_scopes,
    normalize_scopes,
    parse_scopes,
)
from app.domains.ai.service import aware
from app.domains.ai.tokens import (
    ACCESS_PREFIX,
    REFRESH_PREFIX,
    hash_secret,
    new_code,
    new_token,
    pkce_matches,
)

__all__ = [
    "ACCESS_TOKEN_TTL",
    "AuthorizeError",
    "AuthorizeParams",
    "OAuthError",
    "OAuthService",
    "TokenGrant",
    "ValidatedAuthorization",
    "same_resource",
    "server_metadata",
]

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=5)

# S256-challenge — это base64url от SHA-256: ровно 43 символа.
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
# RFC 7636, §4.1: unreserved-символы, 43–128 штук.
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_MAX_STATE = 1000
_MAX_DCR_URIS = 10
_DCR_GRANTS = frozenset({"authorization_code", "refresh_token"})


@dataclass(frozen=True, slots=True)
class AuthorizeParams:
    """Параметры запроса авторизации — как пришли в query string."""

    response_type: str | None = None
    client_id: str | None = None
    redirect_uri: str | None = None
    scope: str | None = None
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    resource: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedAuthorization:
    client: ClientInfo
    redirect_uri: str
    scopes: tuple[str, ...]
    state: str | None
    code_challenge: str
    resource: str


class AuthorizeError(Exception):
    """Запрос авторизации некорректен.

    ``redirect_to`` есть, только когда клиент и адрес возврата
    проверены: вернуть ошибку на непроверенный адрес — открытый
    редирект. Иначе ошибка показывается пользователю на месте.
    """

    def __init__(
        self,
        error: str,
        description: str,
        message: str,
        redirect_to: str | None = None,
    ) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.message = message
        self.redirect_to = redirect_to


class OAuthError(Exception):
    """Ошибка эндпоинта токенов/регистрации в формате RFC 6749."""

    def __init__(
        self, error: str, description: str, status_code: int = 400
    ) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class TokenGrant:
    access_token: str
    refresh_token: str
    expires_in: int
    scopes: tuple[str, ...]

    def as_response(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": join_scopes(self.scopes),
        }


def same_resource(a: str, b: str) -> bool:
    """Ресурсы равны с точностью до завершающего слэша."""
    return a.rstrip("/") == b.rstrip("/")


def _with_query(uri: str, params: list[tuple[str, str | None]]) -> str:
    """Добавить параметры к адресу, сохранив его собственный query."""
    parts = urlsplit(uri)
    extra = urlencode([(k, v) for k, v in params if v is not None])
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit(parts._replace(query=query))


def _without_offline_access(raw: str | None) -> str:
    """Права из запроса без offline_access.

    Его не объявляем: refresh выдаётся и так. Но клиент, который
    всё же его пришлёт, не должен получить invalid_scope.
    """
    return " ".join(s for s in (raw or "").split() if s != "offline_access")


def server_metadata(settings: Settings) -> dict[str, Any]:
    """Метаданные сервера авторизации (RFC 8414)."""
    origin = settings.oauth_issuer
    api = f"{origin}{settings.api_v1_prefix}/ai/oauth"
    return {
        "issuer": origin,
        # Страница согласия — это SPA, а не бэкенд.
        "authorization_endpoint": f"{origin}/oauth/authorize",
        "token_endpoint": f"{api}/token",
        "revocation_endpoint": f"{api}/revoke",
        "registration_endpoint": f"{api}/register",
        "scopes_supported": list(ALL_SCOPES),
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
    }


class OAuthService:
    def __init__(
        self,
        repo: AiRepository,
        settings: Settings,
        fetcher: MetadataFetcher,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._fetcher = fetcher

    # ── Авторизация и согласие ───────────────────────────────────────

    def redirect(
        self,
        redirect_uri: str,
        state: str | None,
        **params: str,
    ) -> str:
        """Адрес возврата с параметрами ответа, state и iss."""
        items: list[tuple[str, str | None]] = list(params.items())
        items.append(("state", state))
        items.append(("iss", self._settings.oauth_issuer))
        return _with_query(redirect_uri, items)

    def deny_redirect(self, v: ValidatedAuthorization) -> str:
        return self.redirect(
            v.redirect_uri,
            v.state,
            error="access_denied",
            error_description="The user denied access",
        )

    async def validate_authorization(
        self, p: AuthorizeParams
    ) -> ValidatedAuthorization:
        """Проверить запрос авторизации целиком.

        Сначала клиент и адрес возврата — пока они не проверены,
        ошибку отдавать некуда. Потом всё остальное, с возвратом
        ошибки клиенту.
        """
        if not p.client_id:
            raise AuthorizeError(
                "invalid_request",
                "client_id is required",
                "В запросе нет client_id — ссылка неполная.",
            )
        try:
            client = await resolve_client(
                p.client_id, self._settings, self._repo, self._fetcher
            )
        except UnknownClientError as exc:
            raise AuthorizeError(
                "invalid_client",
                "Unknown client",
                f"Приложение не распознано: {exc}",
            ) from exc

        uri = p.redirect_uri
        if (
            not uri
            or not is_safe_redirect_uri(uri)
            or not redirect_matches(uri, client.redirect_uris)
        ):
            raise AuthorizeError(
                "invalid_request",
                "redirect_uri is missing or not registered",
                "Адрес возврата не совпадает с зарегистрированным "
                "у приложения. Доступ не выдан.",
            )

        def fail(error: str, description: str, message: str) -> NoReturn:
            raise AuthorizeError(
                error,
                description,
                message,
                redirect_to=self.redirect(
                    uri,
                    p.state,
                    error=error,
                    error_description=description,
                ),
            )

        if p.state is not None and len(p.state) > _MAX_STATE:
            # state слишком длинный — не возвращаем его вовсе.
            raise AuthorizeError(
                "invalid_request",
                "state is too long",
                "Некорректный запрос: слишком длинный state.",
                redirect_to=self.redirect(
                    uri,
                    None,
                    error="invalid_request",
                    error_description="state is too long",
                ),
            )
        if p.response_type != "code":
            fail(
                "unsupported_response_type",
                "Only response_type=code is supported",
                "Приложение просит неподдерживаемый тип ответа.",
            )
        challenge = p.code_challenge or ""
        if p.code_challenge_method != "S256" or not _CHALLENGE_RE.match(
            challenge
        ):
            fail(
                "invalid_request",
                "PKCE with code_challenge_method=S256 is required",
                "Приложение не прислало PKCE (S256).",
            )
        if not p.resource or not same_resource(
            p.resource, self._settings.ai_resource
        ):
            fail(
                "invalid_target",
                "resource must be the anfinances MCP server",
                "Приложение просит доступ не к тому ресурсу.",
            )
        try:
            # Без scope просим всё: пользователь сам снимет галочку
            # записи на странице согласия.
            requested = _without_offline_access(p.scope)
            scopes = parse_scopes(requested) if requested else ALL_SCOPES
        except InvalidScopeError:
            fail(
                "invalid_scope",
                "Unknown scope requested",
                "Приложение просит неизвестные права.",
            )
        if not scopes:
            fail(
                "invalid_scope",
                "No scope requested",
                "Приложение не указало, какие права нужны.",
            )

        return ValidatedAuthorization(
            client=client,
            redirect_uri=uri,
            scopes=scopes,
            state=p.state,
            code_challenge=challenge,
            resource=self._settings.ai_resource,
        )

    async def approve(
        self,
        user_id: uuid.UUID,
        v: ValidatedAuthorization,
        granted: list[str],
        now: datetime,
    ) -> str:
        """Выдать код на одобренные права и вернуть адрес возврата."""
        scopes = normalize_scopes(granted)
        if not scopes or not set(scopes) <= set(v.scopes):
            raise InvalidScopeError(
                "Можно выдать только права, которые просит приложение."
            )
        code = new_code()
        await self._repo.add_code(
            AiAuthCode(
                code_hash=hash_secret(code),
                user_id=user_id,
                client_id=v.client.client_id,
                client_name=v.client.name,
                redirect_uri=v.redirect_uri,
                code_challenge=v.code_challenge,
                scopes=join_scopes(scopes),
                resource=v.resource,
                expires_at=now + CODE_TTL,
            )
        )
        return self.redirect(v.redirect_uri, v.state, code=code)

    # ── Токены ───────────────────────────────────────────────────────

    async def token(self, form: Mapping[str, str]) -> TokenGrant:
        grant_type = form.get("grant_type")
        now = datetime.now(UTC)
        if grant_type == "authorization_code":
            grant = await self._exchange_code(form, now)
        elif grant_type == "refresh_token":
            grant = await self._refresh(form, now)
        elif not grant_type:
            raise OAuthError("invalid_request", "grant_type is required")
        else:
            raise OAuthError(
                "unsupported_grant_type", "Unsupported grant_type"
            )
        await self._repo.delete_expired(now)
        return grant

    def _check_resource(self, form: Mapping[str, str], stored: str) -> None:
        resource = form.get("resource")
        if resource and not same_resource(resource, stored):
            raise OAuthError("invalid_target", "resource mismatch")

    async def _exchange_code(
        self, form: Mapping[str, str], now: datetime
    ) -> TokenGrant:
        code = form.get("code")
        verifier = form.get("code_verifier")
        client_id = form.get("client_id")
        redirect_uri = form.get("redirect_uri")
        if not code or not verifier or not client_id or not redirect_uri:
            raise OAuthError(
                "invalid_request",
                "code, code_verifier, client_id and redirect_uri are required",
            )
        stored = await self._repo.get_code(hash_secret(code), for_update=True)
        if stored is None:
            raise OAuthError("invalid_grant", "Invalid authorization code")
        if stored.used_at is not None:
            # Код предъявлен второй раз: его перехватили или клиент
            # сломан. Выданное по нему подключение больше не верим.
            if stored.connection_id is not None:
                await self._repo.revoke_connection(stored.connection_id, now)
            raise OAuthError("invalid_grant", "Authorization code reused")
        if aware(stored.expires_at) <= now:
            raise OAuthError("invalid_grant", "Authorization code expired")
        if stored.client_id != client_id or stored.redirect_uri != (
            redirect_uri
        ):
            raise OAuthError(
                "invalid_grant", "client_id or redirect_uri mismatch"
            )
        if not _VERIFIER_RE.match(verifier) or not pkce_matches(
            verifier, stored.code_challenge
        ):
            raise OAuthError("invalid_grant", "PKCE verification failed")
        self._check_resource(form, stored.resource)

        stored.used_at = now
        conn = await self._repo.add_connection(
            AiConnection(
                user_id=stored.user_id,
                kind=CONNECTION_OAUTH,
                name=stored.client_name,
                client_id=stored.client_id,
                scopes=stored.scopes,
                resource=stored.resource,
            )
        )
        stored.connection_id = conn.id
        return await self._issue(conn, now)

    async def _refresh(
        self, form: Mapping[str, str], now: datetime
    ) -> TokenGrant:
        raw = form.get("refresh_token")
        client_id = form.get("client_id")
        if not raw or not client_id:
            raise OAuthError(
                "invalid_request", "refresh_token and client_id are required"
            )
        if not raw.startswith(REFRESH_PREFIX):
            raise OAuthError("invalid_grant", "Invalid refresh token")
        token = await self._repo.get_token(hash_secret(raw), for_update=True)
        if token is None or token.kind != TOKEN_REFRESH:
            raise OAuthError("invalid_grant", "Invalid refresh token")
        conn = await self._repo.get_connection(token.connection_id)
        if conn is None or conn.revoked_at is not None:
            raise OAuthError("invalid_grant", "Connection revoked")
        if token.revoked_at is not None:
            # Ротированный refresh пришёл снова — его украли или
            # клиент потерял новый. Не угадаешь, кто настоящий:
            # гасим подключение целиком.
            await self._repo.revoke_connection(conn.id, now)
            raise OAuthError("invalid_grant", "Refresh token reused")
        if token.expires_at is None or aware(token.expires_at) <= now:
            raise OAuthError("invalid_grant", "Refresh token expired")
        if conn.client_id != client_id:
            raise OAuthError("invalid_grant", "client_id mismatch")
        if conn.resource is not None:
            self._check_resource(form, conn.resource)
        requested = _without_offline_access(form.get("scope"))
        if requested:
            try:
                narrowed = parse_scopes(requested)
            except InvalidScopeError as exc:
                raise OAuthError("invalid_scope", "Unknown scope") from exc
            if not set(narrowed) <= set(parse_scopes(conn.scopes)):
                raise OAuthError(
                    "invalid_scope", "Scope exceeds the original grant"
                )

        token.revoked_at = now
        return await self._issue(conn, now)

    async def _issue(self, conn: AiConnection, now: datetime) -> TokenGrant:
        access = new_token(ACCESS_PREFIX)
        refresh = new_token(REFRESH_PREFIX)
        await self._repo.add_token(
            AiToken(
                connection_id=conn.id,
                kind=TOKEN_ACCESS,
                token_hash=hash_secret(access),
                expires_at=now + ACCESS_TOKEN_TTL,
            )
        )
        await self._repo.add_token(
            AiToken(
                connection_id=conn.id,
                kind=TOKEN_REFRESH,
                token_hash=hash_secret(refresh),
                expires_at=now + REFRESH_TOKEN_TTL,
            )
        )
        return TokenGrant(
            access_token=access,
            refresh_token=refresh,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            scopes=parse_scopes(conn.scopes),
        )

    async def revoke(self, form: Mapping[str, str]) -> None:
        """Отзыв по RFC 7009: отзывает подключение целиком.

        Неизвестный токен — не ошибка: ответ должен быть одинаковым,
        иначе эндпоинт стал бы оракулом «есть ли такой токен».
        """
        raw = form.get("token")
        if not raw:
            raise OAuthError("invalid_request", "token is required")
        token = await self._repo.get_token(hash_secret(raw))
        if token is None:
            return
        conn = await self._repo.get_connection(token.connection_id)
        if conn is None:
            return
        client_id = form.get("client_id")
        # Чужой клиент не может отозвать не своё подключение.
        if client_id and conn.client_id and client_id != conn.client_id:
            return
        await self._repo.revoke_connection(conn.id, datetime.now(UTC))

    # ── Динамическая регистрация (RFC 7591) ──────────────────────────

    async def register(self, body: object) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise OAuthError(
                "invalid_client_metadata", "Body must be a JSON object"
            )
        uris = body.get("redirect_uris")
        if (
            not isinstance(uris, list)
            or not uris
            or len(uris) > _MAX_DCR_URIS
            or not all(isinstance(u, str) for u in uris)
        ):
            raise OAuthError(
                "invalid_redirect_uri", "redirect_uris must be a list"
            )
        for uri in uris:
            if not is_allowed_dcr_redirect(uri, self._settings):
                raise OAuthError(
                    "invalid_redirect_uri",
                    "redirect_uri host is not allowed",
                )
        method = body.get("token_endpoint_auth_method", "none")
        if method != "none":
            raise OAuthError(
                "invalid_client_metadata",
                "Only token_endpoint_auth_method=none is supported",
            )
        grants = body.get("grant_types", ["authorization_code"])
        if not isinstance(grants, list) or not set(grants) <= _DCR_GRANTS:
            raise OAuthError(
                "invalid_client_metadata", "Unsupported grant_types"
            )
        responses = body.get("response_types", ["code"])
        if not isinstance(responses, list) or not set(responses) <= {"code"}:
            raise OAuthError(
                "invalid_client_metadata", "Unsupported response_types"
            )
        name = clean_client_name(body.get("client_name"), host_of(uris[0]))

        client = await self._repo.add_client(
            AiOAuthClient(
                client_id="anf_dcr_" + secrets.token_urlsafe(16),
                client_name=name,
                redirect_uris=list(uris),
            )
        )
        return {
            "client_id": client.client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": client.client_name,
            "redirect_uris": list(uris),
            "grant_types": list(grants),
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
