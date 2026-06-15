"""Общие FastAPI-зависимости.

DbSession / SettingsDep — готовые Annotated-типы.
get_current_user — извлекает юзера из access-токена.
Фабрики сервисов собирают доменные сервисы из репозиториев.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.pwned import HibpChecker, PwnedChecker
from app.core.security import TokenError, decode_token
from app.database import get_db
from app.domains.auth.models import User
from app.domains.auth.repository import (
    AuthRepository,
    SqlAuthRepository,
)
from app.domains.auth.service import AuthService

__all__ = [
    "CurrentUser",
    "DbSession",
    "SettingsDep",
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


async def get_current_user(
    settings: SettingsDep,
    repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> User:
    """Достать текущего юзера из access-токена в заголовке."""
    if credentials is None:
        raise UnauthorizedError("Требуется авторизация.")

    try:
        user_id = decode_token(credentials.credentials, settings, "access")
    except TokenError as exc:
        raise UnauthorizedError("Невалидный токен.") from exc

    user = await repo.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Пользователь недоступен.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
