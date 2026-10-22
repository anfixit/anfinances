"""Общие FastAPI-зависимости.

DbSession / SettingsDep — готовые Annotated-типы.
get_current_user — извлекает юзера из access-токена сайта или из
токена ИИ-интеграции (и тогда же проверяет, что этому токену можно).
Фабрики сервисов собирают доменные сервисы из репозиториев.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.exceptions import (
    ForbiddenError,
    RateLimitedError,
    UnauthorizedError,
)
from app.core.pwned import HibpChecker, PwnedChecker
from app.core.security import TokenError, decode_token
from app.database import get_db
from app.domains.ai.policy import deny_reason, is_protocol_path
from app.domains.ai.ratelimit import connection_limiter
from app.domains.ai.repository import SqlAiRepository
from app.domains.ai.scopes import ALL_SCOPES
from app.domains.ai.service import AiAccessService, AiPrincipal
from app.domains.ai.tokens import is_ai_token
from app.domains.auth.models import User
from app.domains.auth.repository import (
    AuthRepository,
    SqlAuthRepository,
)
from app.domains.auth.service import AuthService

__all__ = [
    "AiPrincipalDep",
    "CurrentUser",
    "DbSession",
    "SettingsDep",
    "ai_token_guard",
    "get_ai_principal",
    "get_auth_service",
    "get_current_user",
    "get_db",
    "get_settings",
]

DbSession = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(auto_error=False)


def get_pwned_checker(settings: SettingsDep) -> PwnedChecker:
    return HibpChecker(settings)


def get_auth_repository(db: DbSession) -> AuthRepository:
    return SqlAuthRepository(db)


def get_auth_service(
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    settings: SettingsDep,
    pwned: Annotated[PwnedChecker, Depends(get_pwned_checker)],
) -> AuthService:
    return AuthService(repo, settings, pwned)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _route_path(request: Request) -> str:
    """Шаблон пути сработавшего роута (с префиксом API).

    По шаблону, а не по фактическому адресу, решает политика
    доступа ИИ: в шаблоне нет id и его не обойти кодированием.
    """
    path = getattr(request.scope.get("route"), "path", None)
    return path if isinstance(path, str) else request.url.path


def _bearer_value(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


async def ai_token_guard(request: Request, settings: SettingsDep) -> None:
    """Глобальная проверка: куда токену ИИ нельзя ни при каких правах.

    Висит на всём приложении, потому что часть роутов (/auth/login,
    /auth/refresh) не вызывает get_current_user, и без неё запрос с
    токеном ИИ дошёл бы до них. Здесь — только то, что не зависит от
    прав токена, поэтому без похода в базу; права и сам токен
    проверяет get_current_user.
    """
    token = _bearer_value(request)
    if token is None or not is_ai_token(token):
        return
    request.state.ai_request = True
    path = _route_path(request)
    if is_protocol_path(path, settings.api_v1_prefix):
        return
    reason = deny_reason(
        request.method, path, ALL_SCOPES, settings.api_v1_prefix
    )
    if reason is not None:
        raise ForbiddenError(reason)


async def _authenticate_ai(
    request: Request,
    token: str,
    settings: Settings,
    db: AsyncSession,
) -> AiPrincipal:
    """Проверить токен ИИ, лимит и права на этот запрос."""
    now = datetime.now(UTC)
    service = AiAccessService(SqlAiRepository(db))
    request.state.ai_request = True
    principal = await service.authenticate(token, now)
    # Для строки аудита в middleware и для /ai/whoami.
    request.state.ai_connection_id = principal.connection_id
    request.state.ai_principal = principal

    if not connection_limiter.hit(
        principal.connection_id, settings.ai_rate_limit_per_minute
    ):
        raise RateLimitedError()

    reason = deny_reason(
        request.method,
        _route_path(request),
        principal.scopes,
        settings.api_v1_prefix,
    )
    if reason is not None:
        raise ForbiddenError(reason)

    if await service.touch(principal.connection_id, now):
        # Отдельный commit до работы роута: GET-роуты сами ничего
        # не коммитят, и отметка «использовался» иначе потерялась бы.
        await db.commit()
    return principal


async def get_current_user(
    request: Request,
    settings: SettingsDep,
    db: DbSession,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> User:
    """Достать текущего юзера из токена в заголовке.

    JWT сайта — полный доступ, как и раньше. Токен ИИ-интеграции —
    доступ в пределах его прав (app.domains.ai.policy).
    """
    if credentials is None:
        raise UnauthorizedError("Требуется авторизация.")

    user_id: uuid.UUID
    if is_ai_token(credentials.credentials):
        principal = await _authenticate_ai(
            request, credentials.credentials, settings, db
        )
        user_id = principal.user_id
    else:
        try:
            user_id = decode_token(credentials.credentials, settings, "access")
        except TokenError as exc:
            raise UnauthorizedError("Невалидный токен.") from exc

    user = await repo.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Пользователь недоступен.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_ai_principal(request: Request, user: CurrentUser) -> AiPrincipal:
    """Подключение ИИ, от имени которого пришёл запрос.

    С JWT сайта — 401: этот вход только для токенов ИИ.
    """
    principal = getattr(request.state, "ai_principal", None)
    if not isinstance(principal, AiPrincipal) or principal.user_id != (
        user.id
    ):
        raise UnauthorizedError("Нужен токен ИИ-интеграции.")
    return principal


AiPrincipalDep = Annotated[AiPrincipal, Depends(get_ai_principal)]
