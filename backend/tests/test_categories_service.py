"""Юнит-тесты CategoryService на фейковом репозитории."""

import uuid

import pytest

from app.core.enums import CategoryKind
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.categories.models import Category
from app.domains.categories.schemas import CategoryCreate
from app.domains.categories.service import CategoryService

USER = uuid.uuid4()


class FakeRepo:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Category] = {}

    async def list_active(self, user_id):
        return [
            c
            for c in self.items.values()
            if c.user_id == user_id and not c.is_archived
        ]

    async def get(self, category_id, user_id):
        c = self.items.get(category_id)
        if c is None or c.user_id != user_id:
            return None
        return c

    async def get_active_sibling(self, user_id, parent_id, name):
        for c in self.items.values():
            if (
                c.user_id == user_id
                and c.parent_id == parent_id
                and c.name == name
                and not c.is_archived
            ):
                return c
        return None

    async def has_children(self, category_id):
        return any(
            c.parent_id == category_id and not c.is_archived
            for c in self.items.values()
        )

    async def add(self, category):
        if category.id is None:
            category.id = uuid.uuid4()
        if category.is_archived is None:
            category.is_archived = False
        self.items[category.id] = category
        return category


@pytest.fixture
def service() -> CategoryService:
    return CategoryService(FakeRepo())


def _c(name, kind=CategoryKind.EXPENSE, parent_id=None):
    return CategoryCreate(name=name, kind=kind, parent_id=parent_id)


async def test_create_parent(service: CategoryService) -> None:
    cat = await service.create_category(USER, _c("Еда"))
    assert cat.parent_id is None
    assert cat.kind == CategoryKind.EXPENSE


async def test_subcategory_inherits_kind(
    service: CategoryService,
) -> None:
    parent = await service.create_category(USER, _c("Еда"))
    # пробуем создать подкатегорию с income — должна стать expense
    sub = await service.create_category(
        USER,
        _c("Продукты", kind=CategoryKind.INCOME, parent_id=parent.id),
    )
    assert sub.kind == CategoryKind.EXPENSE


async def test_no_third_level(service: CategoryService) -> None:
    parent = await service.create_category(USER, _c("Еда"))
    sub = await service.create_category(
        USER, _c("Продукты", parent_id=parent.id)
    )
    with pytest.raises(ValidationFailedError):
        await service.create_category(USER, _c("Молоко", parent_id=sub.id))


async def test_duplicate_sibling_name(
    service: CategoryService,
) -> None:
    await service.create_category(USER, _c("Еда"))
    with pytest.raises(AlreadyExistsError):
        await service.create_category(USER, _c("Еда"))


async def test_same_name_different_parents_ok(
    service: CategoryService,
) -> None:
    p1 = await service.create_category(USER, _c("Авто"))
    p2 = await service.create_category(USER, _c("Одежда"))
    await service.create_category(USER, _c("Аксессуары", parent_id=p1.id))
    # то же имя под другим родителем — допустимо
    sub2 = await service.create_category(
        USER, _c("Аксессуары", parent_id=p2.id)
    )
    assert sub2.name == "Аксессуары"


async def test_archive_parent_with_children_blocked(
    service: CategoryService,
) -> None:
    parent = await service.create_category(USER, _c("Еда"))
    await service.create_category(USER, _c("Продукты", parent_id=parent.id))
    with pytest.raises(ValidationFailedError):
        await service.archive_category(parent.id, USER)


async def test_get_missing(service: CategoryService) -> None:
    with pytest.raises(NotFoundError):
        await service.get_category(uuid.uuid4(), USER)


async def test_apply_defaults(service: CategoryService) -> None:
    tree = {"Еда": ["Продукты", "Кафе"], "Авто": ["Топливо"]}
    income = ["Зарплата", "Фриланс"]
    created = await service.apply_defaults(USER, tree, income)
    # 2 родителя + 3 подкат + 2 дохода = 7
    assert created == 7
    items = await service.list_categories(USER)
    assert len(items) == 7
    incomes = [c for c in items if c.kind == CategoryKind.INCOME]
    assert len(incomes) == 2
    assert all(c.parent_id is None for c in incomes)
