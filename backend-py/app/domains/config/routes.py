"""HTTP-роут публичной конфигурации: /config.

Без авторизации: фронтенд читает режим работы до логина, чтобы
решить, показывать ли регистрацию (ADR-025).
"""

from fastapi import APIRouter

from app.core.dependencies import SettingsDep
from app.core.schemas import ApiResponse
from app.domains.config.schemas import ClientConfig

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=ApiResponse[ClientConfig])
async def get_config(settings: SettingsDep) -> ApiResponse[ClientConfig]:
    return ApiResponse(data=ClientConfig(auth_mode=settings.auth_mode))
