"""Rate limiting на чувствительных эндпоинтах (S4, ADR-026).

slowapi поверх in-memory счётчиков процесса. Для self-host (один
uvicorn-воркер) этого достаточно. Для многоворкерного multi_user
нужен общий backend (Redis) через `storage_uri` — отложено до
такого деплоя (YAGNI).

Лимиты читаются из настроек в момент запроса (callable-лимиты),
поэтому конфигурируются через .env без правки кода.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

__all__ = ["ai_register_limit", "limiter", "login_limit", "register_limit"]

limiter = Limiter(key_func=get_remote_address)


def login_limit() -> str:
    return get_settings().rate_limit_login


def register_limit() -> str:
    return get_settings().rate_limit_register


def ai_register_limit() -> str:
    # Динамическая регистрация OAuth-клиентов открыта без входа —
    # лимит не даёт засыпать таблицу клиентов.
    return get_settings().rate_limit_ai_register
