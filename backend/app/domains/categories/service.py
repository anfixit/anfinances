"""Бизнес-логика категорий.

Правила:
- Иерархия строго двухуровневая: у родителя не может быть
  родителя (parent.parent_id обязан быть None).
- Подкатегория наследует kind родителя — нельзя положить
  доходную подкатегорию в расходную.
- Имя уникально среди активных сиблингов (один parent_id).
- Soft-delete; родитель с активными детьми не архивируется.
"""

import uuid

from app.core.enums import CategoryKind
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.categories.models import Category
from app.domains.categories.repository import CategoryRepository
from app.domains.categories.schemas import (
    CategoryCreate,
    CategoryUpdate,
)

__all__ = ["CategoryService"]


class CategoryService:
    def __init__(self, repo: CategoryRepository) -> None:
        self._repo = repo

    async def list_categories(self, user_id: uuid.UUID) -> list[Category]:
        return await self._repo.list_active(user_id)

    async def get_category(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> Category:
        category = await self._repo.get(category_id, user_id)
        if category is None:
            raise NotFoundError("Категория не найдена.")
        return category

    async def create_category(
        self, user_id: uuid.UUID, data: CategoryCreate
    ) -> Category:
        kind = data.kind
        if data.parent_id is not None:
            parent = await self.get_category(data.parent_id, user_id)
            if parent.parent_id is not None:
                raise ValidationFailedError(
                    "Нельзя создать подкатегорию у подкатегории: "
                    "поддерживается только два уровня."
                )
            if parent.is_archived:
                raise ValidationFailedError("Родительская категория в архиве.")
            kind = parent.kind  # наследуем kind родителя

        await self._ensure_unique_name(user_id, data.parent_id, data.name)

        category = Category(
            user_id=user_id,
            name=data.name,
            kind=kind,
            parent_id=data.parent_id,
            icon=data.icon,
            sort_order=data.sort_order,
        )
        return await self._repo.add(category)

    async def update_category(
        self,
        category_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CategoryUpdate,
    ) -> Category:
        category = await self.get_category(category_id, user_id)
        fields = data.model_dump(exclude_unset=True)

        new_name = fields.get("name")
        if new_name is not None and new_name != category.name:
            clash = await self._repo.get_active_sibling(
                user_id, category.parent_id, new_name
            )
            if clash is not None and clash.id != category.id:
                raise AlreadyExistsError(
                    f"Категория «{new_name}» уже есть на этом уровне."
                )

        for key, value in fields.items():
            setattr(category, key, value)
        return category

    async def archive_category(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        category = await self.get_category(category_id, user_id)
        if await self._repo.has_children(category.id):
            raise ValidationFailedError(
                "Сначала удалите или перенесите подкатегории."
            )
        category.is_archived = True

    async def _ensure_unique_name(
        self,
        user_id: uuid.UUID,
        parent_id: uuid.UUID | None,
        name: str,
    ) -> None:
        if await self._repo.get_active_sibling(user_id, parent_id, name):
            raise AlreadyExistsError(
                f"Категория «{name}» уже есть на этом уровне."
            )

    async def apply_defaults(
        self,
        user_id: uuid.UUID,
        expense_tree: dict[str, list[str]],
        income: list[str],
    ) -> int:
        """Создать дефолтный набор категорий новому юзеру.

        Возвращает количество созданных категорий.
        """
        created = 0
        for order, (parent_name, subs) in enumerate(expense_tree.items()):
            parent = await self._repo.add(
                Category(
                    user_id=user_id,
                    name=parent_name,
                    kind=CategoryKind.EXPENSE,
                    parent_id=None,
                    sort_order=order,
                )
            )
            created += 1
            for sub_order, sub_name in enumerate(subs):
                await self._repo.add(
                    Category(
                        user_id=user_id,
                        name=sub_name,
                        kind=CategoryKind.EXPENSE,
                        parent_id=parent.id,
                        sort_order=sub_order,
                    )
                )
                created += 1

        for inc_order, inc_name in enumerate(income):
            await self._repo.add(
                Category(
                    user_id=user_id,
                    name=inc_name,
                    kind=CategoryKind.INCOME,
                    parent_id=None,
                    sort_order=inc_order,
                )
            )
            created += 1

        return created
