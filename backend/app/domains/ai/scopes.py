"""Права ИИ-интеграций (OAuth scopes).

Их всего два, и запись включает чтение: ассистент, которому можно
записать операцию, но нельзя посмотреть счета, всё равно не смог бы
сделать это осмысленно.
"""

from collections.abc import Iterable

__all__ = [
    "ALL_SCOPES",
    "SCOPE_READ",
    "SCOPE_WRITE",
    "InvalidScopeError",
    "join_scopes",
    "normalize_scopes",
    "parse_scopes",
]

SCOPE_READ = "finance.read"
SCOPE_WRITE = "finance.write"
ALL_SCOPES: tuple[str, ...] = (SCOPE_READ, SCOPE_WRITE)


class InvalidScopeError(ValueError):
    """Запрошено право, которого нет."""


def normalize_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    """Проверить права и дополнить запись чтением.

    Возвращает права в каноническом порядке, без повторов.
    """
    requested = set(scopes)
    unknown = requested - set(ALL_SCOPES)
    if unknown:
        raise InvalidScopeError(
            "Неизвестные права: " + ", ".join(sorted(unknown))
        )
    if SCOPE_WRITE in requested:
        requested.add(SCOPE_READ)
    return tuple(scope for scope in ALL_SCOPES if scope in requested)


def parse_scopes(raw: str | None) -> tuple[str, ...]:
    """Разобрать строку прав через пробел (как хранится и в OAuth)."""
    return normalize_scopes((raw or "").split())


def join_scopes(scopes: Iterable[str]) -> str:
    return " ".join(scopes)
