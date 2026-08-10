"""Дерево категорий путями (решение Р-7).

Плоский список имён теряет структуру: «Кофейни» без «Еда» ничего не
говорит ни модели, ни пользователю.
"""

from anfinances_bot.anfinances.schemas import CategoryRead
from anfinances_bot.resolve.categories import (
    build_category_paths,
    find_category_by_path,
)

FOOD = CategoryRead(id="c-1", name="Еда", kind="expense")
COFFEE = CategoryRead(
    id="c-2", name="Кофейни", kind="expense", parent_id="c-1"
)
GROCERIES = CategoryRead(
    id="c-3", name="Продукты", kind="expense", parent_id="c-1"
)
SALARY = CategoryRead(id="c-4", name="Зарплата", kind="income")
ALL = [FOOD, COFFEE, GROCERIES, SALARY]


def test_builds_parent_and_child_paths() -> None:
    paths = build_category_paths(ALL, kind="expense")
    assert {p.path for p in paths} == {
        "Еда",
        "Еда → Кофейни",
        "Еда → Продукты",
    }


def test_filters_by_kind() -> None:
    paths = build_category_paths(ALL, kind="income")
    assert [p.path for p in paths] == ["Зарплата"]


def test_paths_are_sorted() -> None:
    paths = build_category_paths(ALL, kind="expense")
    assert [p.path for p in paths] == sorted(p.path for p in paths)


def test_find_by_exact_path() -> None:
    paths = build_category_paths(ALL, kind="expense")
    found = find_category_by_path(paths, "Еда → Кофейни")
    assert found is not None
    assert found.id == "c-2"


def test_find_is_case_and_space_insensitive() -> None:
    paths = build_category_paths(ALL, kind="expense")
    found = find_category_by_path(paths, "еда→кофейни")
    assert found is not None
    assert found.id == "c-2"


def test_find_unknown_returns_none() -> None:
    paths = build_category_paths(ALL, kind="expense")
    assert find_category_by_path(paths, "Транспорт") is None


def test_orphan_child_keeps_own_name() -> None:
    """Родителя нет в наборе — не теряем категорию совсем."""
    orphan = CategoryRead(
        id="c-9", name="Такси", kind="expense", parent_id="нет-такого"
    )
    paths = build_category_paths([orphan], kind="expense")
    assert [p.path for p in paths] == ["Такси"]


def test_parent_of_other_kind_is_still_used_for_path() -> None:
    """Путь строится по дереву, а фильтр по типу — по самой категории."""
    paths = build_category_paths(ALL, kind="expense")
    assert "Еда → Продукты" in {p.path for p in paths}


def test_empty_tree_gives_empty_paths() -> None:
    assert build_category_paths([], kind="expense") == []
    assert find_category_by_path([], "что угодно") is None
