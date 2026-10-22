"""Что можно делать токену ИИ-интеграции.

Правила собраны в одном месте, а не размазаны по роутам: новый
эндпоинт сразу попадает под них, и забыть закрыть его нельзя.
Решение принимается по методу и шаблону пути роута
(``/api/v1/accounts/{account_id}/restore``), а не по фактическому
адресу — так правила не обойти кодированием или лишним слэшем.

Принцип: ассистент может читать всё и, с правом записи, добавлять
и править операции, бюджеты и цели. Удалять он не может ничего —
ошибку модели, стёршую операцию, пользователь заметит не сразу.
Не трогает он и то, что относится к учётной записи и доступам:
вход, профиль, импорт, полную выгрузку, свои же подключения.
"""

from collections.abc import Collection

from app.domains.ai.scopes import SCOPE_READ, SCOPE_WRITE

__all__ = [
    "READ_METHODS",
    "WELL_KNOWN_PATH",
    "WRITE_METHODS",
    "deny_reason",
    "is_protocol_path",
]

WELL_KNOWN_PATH = "/.well-known/oauth-authorization-server"

READ_METHODS = frozenset({"GET", "HEAD"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH"})

# Последний сегмент пути, по которому меняется архив счетов.
_ARCHIVE_SEGMENTS = frozenset({"archive", "unarchive", "restore"})


def _under(path: str, base: str) -> bool:
    return path == base or path.startswith(base + "/")


def is_protocol_path(path: str, prefix: str) -> bool:
    """Эндпоинты протокола OAuth, куда клиент ходит без Bearer.

    Токен ИИ в заголовке там ничего не открывает, а отказ по нему
    сломал бы клиента, который шлёт заголовок «на всякий случай».
    """
    base = f"{prefix}/ai/oauth"
    return path in {
        f"{base}/token",
        f"{base}/revoke",
        f"{base}/register",
        WELL_KNOWN_PATH,
    }


def deny_reason(
    method: str,
    path: str,
    scopes: Collection[str],
    prefix: str,
) -> str | None:
    """Почему токен ИИ не может выполнить запрос; None — может.

    ``path`` — шаблон пути роута вместе с префиксом API.
    """
    method = method.upper()

    ai_base = f"{prefix}/ai"
    if _under(path, ai_base):
        if path == f"{ai_base}/whoami" and method in READ_METHODS:
            return None
        return "Управлять ИИ-интеграциями можно только в самом приложении."

    if _under(path, f"{prefix}/auth"):
        # /auth/me — единственное исключение: MCP-сервер берёт оттуда
        # часовой пояс и валюту, а менять через него нечего.
        if path == f"{prefix}/auth/me" and method in READ_METHODS:
            return None
        return "Вход и сессии недоступны ИИ-интеграциям."
    if _under(path, f"{prefix}/import"):
        return "Импорт данных доступен только в самом приложении."
    if path == f"{prefix}/export/all.json":
        return "Полная выгрузка доступна только в самом приложении."
    if path == f"{prefix}/currencies/rates/refresh":
        return "Обновлять курсы валют ИИ-интеграциям нельзя."
    if path.rstrip("/").rsplit("/", 1)[-1] in _ARCHIVE_SEGMENTS:
        return "Архив счетов меняется только в самом приложении."
    if _under(path, f"{prefix}/users/me") and method not in READ_METHODS:
        return "Профиль меняется только в самом приложении."

    if method == "DELETE":
        return (
            "ИИ-интеграциям нельзя удалять данные. "
            "Удалите это вручную в приложении."
        )
    if SCOPE_READ not in scopes:
        return "У токена нет права на чтение."
    if method in READ_METHODS:
        return None
    if method in WRITE_METHODS:
        if SCOPE_WRITE in scopes:
            return None
        return "Токен выдан только на чтение: менять данные нельзя."
    return "Этот метод недоступен ИИ-интеграциям."
