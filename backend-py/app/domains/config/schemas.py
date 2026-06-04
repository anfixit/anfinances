"""Pydantic-схемы публичной конфигурации клиента."""

from pydantic import BaseModel

from app.config import AuthMode

__all__ = ["ClientConfig"]


class ClientConfig(BaseModel):
    """Публичные настройки для фронтенда (без секретов).

    Фронт читает их до логина — например, чтобы решить, показывать
    ли регистрацию (в single_user она отключена).
    """

    auth_mode: AuthMode
