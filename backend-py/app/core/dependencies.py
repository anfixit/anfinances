"""Общие FastAPI-зависимости.

get_db — переэкспортирован из app.database для удобства импорта.
get_settings — переэкспортирован из app.config.
get_current_user — заглушка, реализация в шаге 3.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db

# Готовые Annotated-типы, чтобы в роутах писать чище:
#   async def route(db: DbSession, settings: SettingsDep): ...
DbSession = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

__all__ = ["DbSession", "SettingsDep", "get_db", "get_settings"]
