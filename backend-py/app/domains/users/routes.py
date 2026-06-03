"""HTTP-роуты текущего юзера: /users/me/*.

Транзакцией управляет роут (ADR-013). Удаление аккаунта в режиме
single_user запрещено (403) — иначе единственный пользователь
заблокировал бы сам себя.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUser, DbSession, SettingsDep
from app.core.exceptions import ForbiddenError
from app.core.schemas import ApiResponse
from app.domains.auth.schemas import UserRead
from app.domains.users.repository import SqlUserRepository
from app.domains.users.schemas import (
    UserCurrenciesUpdate,
    UserCurrencyRead,
    UserUpdate,
)
from app.domains.users.service import UserService

router = APIRouter(prefix="/users/me", tags=["users"])


def get_user_service(db: DbSession) -> UserService:
    return UserService(SqlUserRepository(db))


ServiceDep = Annotated[UserService, Depends(get_user_service)]


@router.patch("", response_model=ApiResponse[UserRead])
async def update_me(
    data: UserUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[UserRead]:
    updated = await service.update_profile(user.id, data)
    await db.commit()
    return ApiResponse(data=UserRead.model_validate(updated))


@router.delete("", response_model=ApiResponse[dict[str, str]])
async def delete_me(
    user: CurrentUser,
    service: ServiceDep,
    settings: SettingsDep,
    db: DbSession,
) -> ApiResponse[dict[str, str]]:
    if settings.auth_mode == "single_user":
        raise ForbiddenError(
            "Удаление аккаунта недоступно в режиме single_user."
        )
    await service.deactivate(user.id)
    await db.commit()
    return ApiResponse(data={"status": "deactivated"})


@router.get("/currencies", response_model=ApiResponse[list[UserCurrencyRead]])
async def list_my_currencies(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[UserCurrencyRead]]:
    items = await service.list_currencies(user.id)
    return ApiResponse(
        data=[UserCurrencyRead.model_validate(i) for i in items]
    )


@router.put("/currencies", response_model=ApiResponse[list[UserCurrencyRead]])
async def set_my_currencies(
    data: UserCurrenciesUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[list[UserCurrencyRead]]:
    items = await service.set_currencies(user.id, data)
    await db.commit()
    return ApiResponse(
        data=[UserCurrencyRead.model_validate(i) for i in items]
    )
