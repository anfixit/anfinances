"""Бизнес-логика домена budgets.

Месячный план расходов по категории с опциональным переносом
остатка (rollover). Перенос считается на лету, без рекурсии: для
категории с включённым rollover конверт за прошлое =
Σ всех планов − Σ всего потраченного за все месяцы ДО текущего.
Такой подход переживает пропуски месяцев (забытый месяц не обнуляет
накопление), а перерасход уходит в минус и уменьшает следующий
месяц. Бюджет ведётся только по расходным категориям; потраченное
матчится по точному ``category_id``.
"""

import uuid
from datetime import date
from decimal import Decimal

from app.core.datetime import DEFAULT_TIMEZONE, month_bounds_utc
from app.core.enums import CategoryKind
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.budgets.models import Budget
from app.domains.budgets.repository import BudgetRepository
from app.domains.budgets.schemas import (
    BudgetCreate,
    BudgetImport,
    BudgetRead,
    BudgetUpdate,
)
from app.domains.categories.repository import CategoryRepository

__all__ = ["BudgetService"]


class BudgetService:
    def __init__(
        self,
        repo: BudgetRepository,
        categories: CategoryRepository,
    ) -> None:
        self._repo = repo
        self._categories = categories

    async def list_budgets(
        self,
        user_id: uuid.UUID,
        month: str,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> list[BudgetRead]:
        month_date = _month_to_date(month)
        budgets = await self._repo.list_by_month(user_id, month_date)
        return await self._enrich(
            user_id,
            month_date,
            budgets,
            timezone_name,
        )

    async def create_budget(
        self,
        user_id: uuid.UUID,
        data: BudgetCreate,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> BudgetRead:
        month_date = _month_to_date(data.month)
        await self._validate_category(user_id, data.category_id)
        existing = await self._repo.get_by_month_category(
            user_id, month_date, data.category_id
        )
        if existing is not None:
            raise AlreadyExistsError(
                "Бюджет на этот месяц по этой категории уже есть."
            )
        budget = await self._repo.add(
            Budget(
                user_id=user_id,
                month=month_date,
                category_id=data.category_id,
                planned=data.planned,
                notes=data.notes,
                rollover=data.rollover,
            )
        )
        views = await self._enrich(
            user_id,
            month_date,
            [budget],
            timezone_name,
        )
        return views[0]

    async def update_budget(
        self,
        budget_id: uuid.UUID,
        user_id: uuid.UUID,
        data: BudgetUpdate,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> BudgetRead:
        budget = await self._get(budget_id, user_id)
        fields = data.model_dump(exclude_unset=True)
        for key, value in fields.items():
            setattr(budget, key, value)
        views = await self._enrich(
            user_id,
            budget.month,
            [budget],
            timezone_name,
        )
        return views[0]

    async def delete_budget(
        self, budget_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        budget = await self._get(budget_id, user_id)
        await self._repo.delete(budget)

    async def import_budgets(
        self,
        user_id: uuid.UUID,
        data: BudgetImport,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> list[BudgetRead]:
        month_date = _month_to_date(data.month)
        for item in data.items:
            await self._validate_category(user_id, item.category_id)
            existing = await self._repo.get_by_month_category(
                user_id, month_date, item.category_id
            )
            if existing is None:
                await self._repo.add(
                    Budget(
                        user_id=user_id,
                        month=month_date,
                        category_id=item.category_id,
                        planned=item.planned,
                        notes=item.notes,
                        rollover=item.rollover,
                    )
                )
            else:
                existing.planned = item.planned
                existing.notes = item.notes
                existing.rollover = item.rollover
        budgets = await self._repo.list_by_month(user_id, month_date)
        return await self._enrich(
            user_id,
            month_date,
            budgets,
            timezone_name,
        )

    async def _get(self, budget_id: uuid.UUID, user_id: uuid.UUID) -> Budget:
        budget = await self._repo.get(budget_id, user_id)
        if budget is None:
            raise NotFoundError("Бюджет не найден.")
        return budget

    async def _validate_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        category = await self._categories.get(category_id, user_id)
        if category is None:
            raise NotFoundError("Категория не найдена.")
        if category.is_archived:
            raise ValidationFailedError("Категория в архиве.")
        if category.kind != CategoryKind.EXPENSE:
            raise ValidationFailedError(
                "Бюджет ведётся только по расходным категориям."
            )

    async def _enrich(
        self,
        user_id: uuid.UUID,
        month_date: date,
        budgets: list[Budget],
        timezone_name: str,
    ) -> list[BudgetRead]:
        if not budgets:
            return []
        start, end = month_bounds_utc(month_date, timezone_name)
        spent_month = await self._repo.spent_by_category(user_id, start, end)
        need_rollover = any(b.rollover for b in budgets)
        planned_before: dict[uuid.UUID, Decimal] = {}
        spent_before: dict[uuid.UUID, Decimal] = {}
        if need_rollover:
            planned_before = await self._repo.planned_before(
                user_id, month_date
            )
            spent_before = await self._repo.spent_before(user_id, start)

        views: list[BudgetRead] = []
        for budget in budgets:
            # Расход хранится со знаком минус; для показа — модуль.
            spent = abs(spent_month.get(budget.category_id, Decimal(0)))
            if budget.rollover:
                before_planned = planned_before.get(
                    budget.category_id, Decimal(0)
                )
                # spent_before со знаком (расход < 0): план + расход
                # даёт «план минус потрачено» за всё прошлое.
                before_spent = spent_before.get(budget.category_id, Decimal(0))
                rollover_amount = before_planned + before_spent
            else:
                rollover_amount = Decimal(0)
            available = budget.planned + rollover_amount
            views.append(
                BudgetRead(
                    id=budget.id,
                    month=_date_to_month(budget.month),
                    category_id=budget.category_id,
                    planned=budget.planned,
                    notes=budget.notes,
                    rollover=budget.rollover,
                    rollover_amount=rollover_amount,
                    available=available,
                    spent=spent,
                    remaining=available - spent,
                    created_at=budget.created_at,
                    updated_at=budget.updated_at,
                )
            )
        return views


def _month_to_date(month: str) -> date:
    """'YYYY-MM' → первое число месяца."""
    year, mon = month.split("-")
    return date(int(year), int(mon), 1)


def _date_to_month(value: date) -> str:
    """date → 'YYYY-MM'."""
    return f"{value.year:04d}-{value.month:02d}"
