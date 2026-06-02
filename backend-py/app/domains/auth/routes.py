"""HTTP-роуты аутентификации: /auth/*.

Транзакцией управляет роут: сервис делает flush, успешный
ответ фиксируется commit. Регистрация доступна только когда
AUTH_MODE разрешает (single_user отдаёт 403).
"""

from fastapi import APIRouter, status

from app.core.dependencies import (
    AuthServiceDep,
    CurrentUser,
    DbSession,
    SettingsDep,
)
from app.core.exceptions import ForbiddenError
from app.core.schemas import ApiResponse
from app.domains.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[TokenPair],
)
async def register(
    data: RegisterRequest,
    service: AuthServiceDep,
    settings: SettingsDep,
    db: DbSession,
) -> ApiResponse[TokenPair]:
    if settings.auth_mode == "single_user":
        raise ForbiddenError("Регистрация отключена в режиме single_user.")
    _user, tokens = await service.register(
        data.email, data.password, data.name
    )
    await db.commit()
    return ApiResponse(data=tokens)


@router.post("/login", response_model=ApiResponse[TokenPair])
async def login(
    data: LoginRequest,
    service: AuthServiceDep,
    db: DbSession,
) -> ApiResponse[TokenPair]:
    _user, tokens = await service.login(data.email, data.password)
    await db.commit()
    return ApiResponse(data=tokens)


@router.post("/refresh", response_model=ApiResponse[TokenPair])
async def refresh(
    data: RefreshRequest,
    service: AuthServiceDep,
    db: DbSession,
) -> ApiResponse[TokenPair]:
    tokens = await service.refresh(data.refresh_token)
    await db.commit()
    return ApiResponse(data=tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[dict[str, str]],
)
async def logout(
    data: RefreshRequest,
    service: AuthServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    await service.logout(data.refresh_token)
    await db.commit()
    return ApiResponse(data={"status": "logged_out"})


@router.get("/me", response_model=ApiResponse[UserRead])
async def me(user: CurrentUser) -> ApiResponse[UserRead]:
    return ApiResponse(data=UserRead.model_validate(user))
