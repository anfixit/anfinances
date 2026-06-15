"""HTTP-роуты аутентификации: /auth/*.

Транзакцией управляет роут: сервис делает flush, успешный ответ
фиксируется commit. Регистрация доступна только когда AUTH_MODE
разрешает (single_user отдаёт 403).

Refresh-токен живёт в HttpOnly-cookie (ADR-024): сервис отдаёт пару
токенов, роут кладёт refresh в cookie, а в тело — только access.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.config import Settings
from app.core.dependencies import (
    AuthServiceDep,
    CurrentUser,
    DbSession,
    SettingsDep,
)
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.schemas import ApiResponse
from app.domains.auth.schemas import (
    AccessToken,
    LoginRequest,
    RegisterRequest,
    UserRead,
)
from app.domains.categories.defaults import (
    DEFAULT_EXPENSE_TREE,
    DEFAULT_INCOME,
)
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.categories.service import CategoryService

REFRESH_COOKIE_NAME = "refresh_token"
SECONDS_PER_DAY = 86400

router = APIRouter(prefix="/auth", tags=["auth"])


def _refresh_cookie_path(settings: Settings) -> str:
    # Cookie уходит только на /auth/* — минимизируем поверхность.
    return f"{settings.api_v1_prefix}/auth"


def _set_refresh_cookie(
    response: Response,
    settings: Settings,
    token: str,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.refresh_token_expire_days * SECONDS_PER_DAY,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=_refresh_cookie_path(settings),
    )


def _clear_refresh_cookie(
    response: Response,
    settings: Settings,
) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=_refresh_cookie_path(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AccessToken],
)
async def register(
    data: RegisterRequest,
    service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
    response: Response,
) -> ApiResponse[AccessToken]:
    if settings.auth_mode == "single_user":
        raise ForbiddenError("Регистрация отключена в режиме single_user.")

    user, tokens = await service.register(data.email, data.password, data.name)

    cat_service = CategoryService(SqlCategoryRepository(db))
    await cat_service.apply_defaults(
        user.id,
        DEFAULT_EXPENSE_TREE,
        DEFAULT_INCOME,
    )

    await db.commit()
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ApiResponse(data=AccessToken(access_token=tokens.access_token))


@router.post("/login", response_model=ApiResponse[AccessToken])
async def login(
    data: LoginRequest,
    service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
    response: Response,
) -> ApiResponse[AccessToken]:
    _user, tokens = await service.login(data.email, data.password)
    await db.commit()
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ApiResponse(data=AccessToken(access_token=tokens.access_token))


@router.post("/refresh", response_model=ApiResponse[AccessToken])
async def refresh(
    service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> ApiResponse[AccessToken]:
    if refresh_token is None:
        raise UnauthorizedError("Нет refresh-токена.")

    tokens = await service.refresh(refresh_token)
    await db.commit()
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ApiResponse(data=AccessToken(access_token=tokens.access_token))


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[dict[str, str]],
)
async def logout(
    service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> ApiResponse[dict[str, str]]:
    if refresh_token is not None:
        await service.logout(refresh_token)
        await db.commit()
    _clear_refresh_cookie(response, settings)
    return ApiResponse(data={"status": "logged_out"})


@router.get("/me", response_model=ApiResponse[UserRead])
async def me(user: CurrentUser) -> ApiResponse[UserRead]:
    return ApiResponse(data=UserRead.model_validate(user))
