"""Бизнес-логика домена budgets.

Месячный план расходов по категории с опциональным переносом
остатка (rollover). Перенос считается на лету, без рекурсии: для
категории с включённым rollover конверт за прошлое =
Σ всех планов − Σ всего потраченного за все месяцы ДО текущего.
Такой подход переживает пропуски месяцев (забытый месяц не обнуляет
накопление), а перерасход уходит в минус и уменьшает следующий
месяц. Бюджет ведётся только по расходным категориям. Бюджет
родительской категории включает расходы её подкатегорий, а бюджет
подкатегории учитывает только собственные расходы.
"""

import uuid
from datetime import date, datetime
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
from app.domains.categories.models import Category
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

    async def envelope_without_plan(
        self,
        user_id: uuid.UUID,
        month: str,
        category_ids: list[uuid.UUID],
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> dict[uuid.UUID, Decimal]:
        """Сколько лежит в конверте, если на этот месяц плана ещё нет.

        Цели к дате нужно накопленное. Бюджет на новый месяц заводят
        не первого числа, и без строки бюджета цель считала бы, что в
        копилке ноль, — и требовала бы взнос заново, как с нуля. Тут
        та же формула, что у переноса остатка: все прошлые планы плюс
        всё потраченное, включая этот месяц.
        """
        if not category_ids:
            return {}
        month_date = _month_to_date(month)
        start, end = month_bounds_utc(month_date, timezone_name)
        scopes = _build_category_scopes(
            await self._categories.list_all(user_id)
        )
        planned = await self._repo.planned_before(user_id, month_date)
        windows = await self._spent_since_envelope_start(
            user_id, category_ids, start, timezone_name
        )
        spent_month = await self._repo.spent_by_category(user_id, start, end)
        result: dict[uuid.UUID, Decimal] = {}
        for category_id in category_ids:
            scope = scopes.get(category_id, frozenset({category_id}))
            spent_before = windows[category_id]
            spent = sum(
                (
                    spent_before.get(c, Decimal(0))
                    + spent_month.get(c, Decimal(0))
                    for c in scope
                ),
                start=Decimal(0),
            )
            # Траты отрицательные — сумма и есть остаток в конверте.
            result[category_id] = planned.get(category_id, Decimal(0)) + spent
        return result

    async def move_planned(
        self,
        user_id: uuid.UUID,
        *,
        month: str,
        from_category_id: uuid.UUID,
        to_category_id: uuid.UUID,
        amount: Decimal,
    ) -> None:
        """Перенести часть плана из одной категории в другую.

        Третье правило ВНБ: перерасход закрывается не виной, а
        пересборкой плана. Сумма планов при этом не меняется — деньги
        не появляются, а меняют назначение, поэтому перенос и не
        трогает ни операции, ни остатки счетов.
        """
        if amount <= 0:
            raise ValidationFailedError(
                "Сумма переноса должна быть больше нуля."
            )
        if from_category_id == to_category_id:
            raise ValidationFailedError(
                "Категория-источник и получатель должны различаться."
            )

        month_date = _month_to_date(month)
        await self._validate_category(user_id, from_category_id)
        await self._validate_category(user_id, to_category_id)

        source = await self._repo.get_by_month_category(
            user_id, month_date, from_category_id
        )
        if source is None:
            raise ValidationFailedError(
                "У категории-источника нет плана на этот месяц."
            )
        if source.planned < amount:
            raise ValidationFailedError(
                f"В плане категории-источника только {source.planned}."
            )

        target = await self._repo.get_by_month_category(
            user_id, month_date, to_category_id
        )
        source.planned -= amount
        if target is None:
            await self._repo.add(
                Budget(
                    user_id=user_id,
                    month=month_date,
                    category_id=to_category_id,
                    planned=amount,
                )
            )
        else:
            target.planned += amount

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
        # Архивные тоже: подкатегорию убрали в архив, а её траты этого
        # и прошлых месяцев из конверта родителя никуда не делись.
        categories = await self._categories.list_all(user_id)
        category_scopes = _build_category_scopes(categories)
        spent_month = await self._repo.spent_by_category(user_id, start, end)
        rolling = [b.category_id for b in budgets if b.rollover]
        planned_before: dict[uuid.UUID, Decimal] = {}
        windows: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
        if rolling:
            planned_before = await self._repo.planned_before(
                user_id, month_date
            )
            windows = await self._spent_since_envelope_start(
                user_id, rolling, start, timezone_name
            )

        views: list[BudgetRead] = []
        for budget in budgets:
            scope = category_scopes.get(
                budget.category_id,
                frozenset({budget.category_id}),
            )
            spent_value = sum(
                (
                    spent_month.get(category_id, Decimal(0))
                    for category_id in scope
                ),
                start=Decimal(0),
            )
            # Возврат возвращает деньги в конверт. abs сделал бы из
            # месяца с одним только возвратом перерасход.
            spent = -spent_value
            if budget.rollover:
                before_planned = planned_before.get(
                    budget.category_id, Decimal(0)
                )
                spent_before = windows[budget.category_id]
                before_spent = sum(
                    (
                        spent_before.get(category_id, Decimal(0))
                        for category_id in scope
                    ),
                    start=Decimal(0),
                )
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

    async def _spent_since_envelope_start(
        self,
        user_id: uuid.UUID,
        envelopes: list[uuid.UUID],
        start: datetime,
        timezone_name: str,
    ) -> dict[uuid.UUID, dict[uuid.UUID, Decimal]]:
        """Траты до ``start`` по категориям — с начала каждого конверта.

        Конверт начинается с первого месяца, когда на его категорию
        поставили план. Раньше сюда шли все траты с начала истории, и
        конверт, впервые заведённый спустя год, сразу показывал
        перерасход на всю прошлую жизнь категории. Планы и так считаются
        только по бюджетам, теперь и траты — с той же даты.
        """
        firsts = await self._repo.first_budget_months(user_id)
        by_since: dict[datetime, dict[uuid.UUID, Decimal]] = {}
        result: dict[uuid.UUID, dict[uuid.UUID, Decimal]] = {}
        for envelope in envelopes:
            first = firsts.get(envelope)
            if first is None:
                result[envelope] = {}
                continue
            since, _ = month_bounds_utc(first, timezone_name)
            if since >= start:
                result[envelope] = {}
                continue
            if since not in by_since:
                by_since[since] = await self._repo.spent_before(
                    user_id, start, since=since
                )
            result[envelope] = by_since[since]
        return result


def _build_category_scopes(
    categories: list[Category],
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    """Вернуть категории, расходы которых входят в каждый бюджет."""
    children: dict[uuid.UUID, set[uuid.UUID]] = {}
    for category in categories:
        if category.parent_id is not None:
            children.setdefault(category.parent_id, set()).add(category.id)

    return {
        category.id: frozenset(
            {category.id, *children.get(category.id, set())}
        )
        for category in categories
    }


def _month_to_date(month: str) -> date:
    """'YYYY-MM' → первое число месяца."""
    year, mon = month.split("-")
    return date(int(year), int(mon), 1)


def _date_to_month(value: date) -> str:
    """date → 'YYYY-MM'."""
    return f"{value.year:04d}-{value.month:02d}"
