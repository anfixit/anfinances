"""Дерево категорий в виде путей (решение Р-7).

Плоский список имён теряет структуру: «Кофейни» без «Еда» ничего не
говорит ни модели, ни пользователю. Пути вида «Еда → Кофейни» решают
и это, и показ в карточке операции.
"""

from dataclasses import dataclass

from anfinances_bot.anfinances.schemas import CategoryRead

__all__ = [
    "SEPARATOR",
    "CategoryPath",
    "build_category_paths",
    "find_category_by_path",
]

SEPARATOR = " → "


@dataclass(frozen=True)
class CategoryPath:
    id: str
    path: str


def build_category_paths(
    categories: list[CategoryRead], kind: str
) -> list[CategoryPath]:
    """Построить отсортированные пути для категорий нужного типа."""
    by_id = {c.id: c for c in categories}
    paths: list[CategoryPath] = []
    for category in categories:
        if category.kind != kind:
            continue
        parent = (
            by_id.get(category.parent_id)
            if category.parent_id is not None
            else None
        )
        path = (
            f"{parent.name}{SEPARATOR}{category.name}"
            if parent is not None
            else category.name
        )
        paths.append(CategoryPath(id=category.id, path=path))
    paths.sort(key=lambda p: p.path)
    return paths


def find_category_by_path(
    paths: list[CategoryPath], path: str
) -> CategoryPath | None:
    """Найти категорию по пути, игнорируя регистр и пробелы."""
    needle = _normalize(path)
    for candidate in paths:
        if _normalize(candidate.path) == needle:
            return candidate
    return None


def _normalize(value: str) -> str:
    return value.casefold().replace(" ", "")
