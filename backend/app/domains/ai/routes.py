"""HTTP-роуты ИИ-интеграций: /ai/* и метаданные OAuth.

Три группы:

* /ai/whoami — для MCP-сервера: чей это токен и что ему можно.
* /ai/connections и /ai/oauth/authorize/* — управление и согласие,
  только с JWT сайта (токенам ИИ их закрывает политика доступа).
* /ai/oauth/token|revoke|register и /.well-known/… — протокол OAuth.
  Формат ответов там задают RFC, а не конверт ApiResponse.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.dependencies import (
    AiPrincipalDep,
    CurrentUser,
    DbSession,
    SettingsDep,
)
from app.core.exceptions import ValidationFailedError
from app.core.rate_limit import ai_register_limit, limiter
from app.core.schemas import ApiResponse
from app.domains.ai.clients import (
    HttpxMetadataFetcher,
    MetadataFetcher,
    host_of,
)
from app.domains.ai.oauth import (
    AuthorizeError,
    AuthorizeParams,
    OAuthError,
    OAuthService,
    server_metadata,
)
from app.domains.ai.policy import WELL_KNOWN_PATH
from app.domains.ai.repository import SqlAiRepository
from app.domains.ai.schemas import (
    AiConnectionRead,
    AiWhoAmI,
    AuthorizeApprove,
    AuthorizeCheck,
    AuthorizeRedirect,
    PersonalTokenCreate,
    PersonalTokenCreated,
)
from app.domains.ai.scopes import InvalidScopeError, normalize_scopes
from app.domains.ai.service import AiAccessService

router = APIRouter(prefix="/ai", tags=["ai"])
well_known_router = APIRouter(tags=["oauth"])

# Ответы с токенами и ошибки протокола не должны оседать в кешах.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def get_metadata_fetcher(settings: SettingsDep) -> MetadataFetcher:
    return HttpxMetadataFetcher(settings)


def get_access_service(db: DbSession) -> AiAccessService:
    return AiAccessService(SqlAiRepository(db))


def get_oauth_service(
    db: DbSession,
    settings: SettingsDep,
    fetcher: Annotated[MetadataFetcher, Depends(get_metadata_fetcher)],
) -> OAuthService:
    return OAuthService(SqlAiRepository(db), settings, fetcher)


AccessDep = Annotated[AiAccessService, Depends(get_access_service)]
OAuthDep = Annotated[OAuthService, Depends(get_oauth_service)]


def _oauth_error(exc: OAuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "error_description": exc.description},
        headers=_NO_STORE,
    )


async def _read_form(request: Request) -> dict[str, str]:
    """Тело x-www-form-urlencoded как словарь строк.

    Повтор параметра — ошибка (RFC 6749, §3.2): иначе непонятно,
    какое из значений проверять.
    """
    form = await request.form()
    result: dict[str, str] = {}
    for key in form:
        values = form.getlist(key)
        if len(values) != 1 or not isinstance(values[0], str):
            raise OAuthError("invalid_request", f"Repeated parameter {key}")
        result[key] = values[0]
    return result


# ── Метаданные ───────────────────────────────────────────────────────


@well_known_router.get(WELL_KNOWN_PATH, include_in_schema=False)
async def authorization_server_metadata(
    settings: SettingsDep,
) -> JSONResponse:
    return JSONResponse(
        server_metadata(settings),
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Для MCP-сервера ──────────────────────────────────────────────────


@router.get("/whoami", response_model=ApiResponse[AiWhoAmI])
async def whoami(principal: AiPrincipalDep) -> ApiResponse[AiWhoAmI]:
    """Чей токен и что ему можно. С JWT сайта — 401."""
    return ApiResponse(
        data=AiWhoAmI(
            connection_id=principal.connection_id,
            user_id=principal.user_id,
            scopes=list(principal.scopes),
            kind="oauth" if principal.kind == "oauth" else "personal",
            name=principal.name,
            client_id=principal.client_id,
            resource=principal.resource,
            expires_at=principal.expires_at,
        )
    )


# ── Управление подключениями ─────────────────────────────────────────


@router.get("/connections", response_model=ApiResponse[list[AiConnectionRead]])
async def list_connections(
    user: CurrentUser, service: AccessDep
) -> ApiResponse[list[AiConnectionRead]]:
    conns = await service.list_connections(user.id)
    return ApiResponse(data=[AiConnectionRead.from_model(c) for c in conns])


@router.post(
    "/connections",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PersonalTokenCreated],
)
async def create_personal_token(
    data: PersonalTokenCreate,
    user: CurrentUser,
    service: AccessDep,
    settings: SettingsDep,
    db: DbSession,
) -> ApiResponse[PersonalTokenCreated]:
    """Личный токен. Сам токен показывается в ответе один раз."""
    conn, raw = await service.create_personal_token(
        user.id,
        data.name,
        normalize_scopes(data.scopes),
        settings.ai_resource,
    )
    await db.commit()
    return ApiResponse(
        data=PersonalTokenCreated(
            connection=AiConnectionRead.from_model(conn), token=raw
        )
    )


@router.post(
    "/connections/{connection_id}/revoke",
    response_model=ApiResponse[dict[str, str]],
)
async def revoke_connection(
    connection_id: uuid.UUID,
    user: CurrentUser,
    service: AccessDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.revoke(user.id, connection_id, datetime.now(UTC))
    await db.commit()
    return ApiResponse(data={"status": "revoked"})


# ── Согласие (вызывает SPA-страница /oauth/authorize) ────────────────


def authorize_params(
    response_type: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    scope: str | None = None,
    state: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    resource: str | None = None,
) -> AuthorizeParams:
    return AuthorizeParams(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resource,
    )


@router.get(
    "/oauth/authorize/check", response_model=ApiResponse[AuthorizeCheck]
)
async def check_authorization(
    params: Annotated[AuthorizeParams, Depends(authorize_params)],
    user: CurrentUser,
    oauth: OAuthDep,
) -> ApiResponse[AuthorizeCheck]:
    """Проверить запрос авторизации и сказать, что показать."""
    try:
        v = await oauth.validate_authorization(params)
    except AuthorizeError as exc:
        return ApiResponse(
            data=AuthorizeCheck(
                status="error",
                error=exc.error,
                message=exc.message,
                redirect_to=exc.redirect_to,
            )
        )
    return ApiResponse(
        data=AuthorizeCheck(
            status="ok",
            client_id=v.client.client_id,
            client_name=v.client.name,
            redirect_host=host_of(v.redirect_uri),
            scopes=list(v.scopes),
            deny_redirect_to=oauth.deny_redirect(v),
        )
    )


@router.post(
    "/oauth/authorize/approve",
    response_model=ApiResponse[AuthorizeRedirect],
)
async def approve_authorization(
    data: AuthorizeApprove,
    user: CurrentUser,
    oauth: OAuthDep,
    db: DbSession,
) -> ApiResponse[AuthorizeRedirect]:
    """«Разрешить»: выдать код и вернуть адрес возврата.

    Запрос проверяется заново целиком: страница согласия могла
    висеть открытой, а между проверкой и кликом — что угодно.
    """
    params = AuthorizeParams(**data.model_dump(exclude={"scopes"}))
    try:
        v = await oauth.validate_authorization(params)
    except AuthorizeError as exc:
        if exc.redirect_to is not None:
            return ApiResponse(
                data=AuthorizeRedirect(redirect_to=exc.redirect_to)
            )
        raise ValidationFailedError(exc.message) from exc
    try:
        redirect_to = await oauth.approve(
            user.id, v, list(data.scopes), datetime.now(UTC)
        )
    except InvalidScopeError as exc:
        raise ValidationFailedError(str(exc)) from exc
    await db.commit()
    return ApiResponse(data=AuthorizeRedirect(redirect_to=redirect_to))


# ── Протокол OAuth ───────────────────────────────────────────────────


@router.post("/oauth/token", include_in_schema=False)
async def token(request: Request, oauth: OAuthDep, db: DbSession) -> Response:
    """Обмен кода и refresh-токена (RFC 6749, §4.1.3 и §6)."""
    try:
        grant = await oauth.token(await _read_form(request))
    except OAuthError as exc:
        # Ошибка могла отозвать подключение (повтор кода или
        # refresh) — это нужно сохранить, хотя ответ и ошибка.
        await db.commit()
        return _oauth_error(exc)
    await db.commit()
    return JSONResponse(grant.as_response(), headers=_NO_STORE)


@router.post("/oauth/revoke", include_in_schema=False)
async def revoke(request: Request, oauth: OAuthDep, db: DbSession) -> Response:
    """Отзыв токена (RFC 7009). На неизвестный токен — тоже 200."""
    try:
        await oauth.revoke(await _read_form(request))
    except OAuthError as exc:
        return _oauth_error(exc)
    await db.commit()
    return Response(status_code=status.HTTP_200_OK, headers=_NO_STORE)


@router.post("/oauth/register", include_in_schema=False)
@limiter.limit(ai_register_limit)
async def register_client(
    request: Request, oauth: OAuthDep, db: DbSession
) -> Response:
    """Динамическая регистрация клиента (RFC 7591)."""
    body: Any
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    try:
        client = await oauth.register(body)
    except OAuthError as exc:
        return _oauth_error(exc)
    await db.commit()
    return JSONResponse(
        client, status_code=status.HTTP_201_CREATED, headers=_NO_STORE
    )
