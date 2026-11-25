"""HTTP-роуты корзины: /trash/*.

Здесь же зависимости для роутов удаления в других доменах: сервис
корзины и «кто удаляет».
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import CurrentUser, DbSession, is_ai_request
from app.core.schemas import ApiResponse
from app.domains.trash.repository import SqlTrashRepository
from app.domains.trash.schemas import DeletedRecordRead
from app.domains.trash.service import Deleter, TrashService

__all__ = ["DeleterDep", "TrashServiceDep", "router"]

router = APIRouter(prefix="/trash", tags=["trash"])


def get_trash_service(db: DbSession, user: CurrentUser) -> TrashService:
    return TrashService(SqlTrashRepository(db), user.timezone or "UTC")


def get_deleter(request: Request, user: CurrentUser) -> Deleter:
    """Кто удаляет. Зависит от CurrentUser — он и кладёт принципала ИИ.

    Параметр ``user`` нужен ради порядка: проверка токена должна
    отработать раньше, чем мы спросим, чей это токен.
    """
    principal = getattr(request.state, "ai_principal", None)
    if principal is not None:
        return Deleter(
            source=f"ИИ: {principal.name}",
            ai=True,
            ai_connection_id=principal.connection_id,
        )
    if is_ai_request(request):
        return Deleter(source="ИИ-интеграция", ai=True)
    return Deleter(source="Сайт")


TrashServiceDep = Annotated[TrashService, Depends(get_trash_service)]
DeleterDep = Annotated[Deleter, Depends(get_deleter)]


@router.get("", response_model=ApiResponse[list[DeletedRecordRead]])
async def list_trash(
    user: CurrentUser,
    service: TrashServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApiResponse[list[DeletedRecordRead]]:
    """Что лежит в корзине, свежее сверху. Возвращённое не показывается."""
    items = await service.list_waiting(user.id, limit)
    return ApiResponse(
        data=[DeletedRecordRead.model_validate(item) for item in items]
    )


@router.post(
    "/{record_id}/restore", response_model=ApiResponse[DeletedRecordRead]
)
async def restore_from_trash(
    record_id: uuid.UUID,
    user: CurrentUser,
    service: TrashServiceDep,
    db: DbSession,
) -> ApiResponse[DeletedRecordRead]:
    """Вернуть удалённое на место — с теми же id."""
    record = await service.restore(record_id, user.id)
    await db.commit()
    return ApiResponse(data=DeletedRecordRead.model_validate(record))
