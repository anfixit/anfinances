"""Бизнес-логика целей по категориям.

Главное здесь — одна формула: сколько положить в конверт в этом
месяце, чтобы прийти к цели вовремя.

Считается от уже накопленного, а не от нуля: если в конверте лежит
40 000 из 60 000, взнос должен упасть, а не остаться прежним. Иначе
цель врёт, и ей перестают верить.

Округление вверх, до копейки: делить 60 000 на 7 месяцев и класть по
8 571,42 — значит не дойти до цели на копейку и удивиться в декабре.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal

from app.core.enums import GoalKind
from app.core.exceptions import NotFoundError
from app.domains.budgets.schemas import BudgetRead
from app.domains.categories.repository import CategoryRepository
from app.domains.goals.models import CategoryGoal
from app.domains.goals.repository import GoalRepository
from app.domains.goals.schemas import GoalUpsert

__all__ = ["GoalProgress", "GoalService", "months_between"]

_CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class GoalProgress:
    """Цель вместе с расчётом на конкретный месяц."""

    goal: CategoryGoal
    accumulated: Decimal
    need_this_month: Decimal
    planned_this_month: Decimal
    still_to_add: Decimal
    months_left: int
    is_reached: bool


def months_between(start: date, end: date) -> int:
    """Сколько месяцев осталось, считая текущий.

    Дата в прошлом — значит нужно всё сейчас, а не «минус два
    месяца»: отрицательный делитель дал бы отрицательный взнос.
    """
    diff = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return max(diff, 1)


class GoalService:
    def __init__(
        self, repo: GoalRepository, categories: CategoryRepository
    ) -> None:
        self._repo = repo
        self._categories = categories

    async def upsert_goal(
        self, user_id: uuid.UUID, data: GoalUpsert
    ) -> CategoryGoal:
        category = await self._categories.get(data.category_id, user_id)
        if category is None:
            raise NotFoundError("Категория не найдена.")

        existing = await self._repo.get_by_category(user_id, data.category_id)
        if existing is not None:
            existing.kind = data.kind
            existing.amount = data.amount
            existing.target_date = data.target_date
            return existing
        return await self._repo.add(
            CategoryGoal(
                user_id=user_id,
                category_id=data.category_id,
                kind=data.kind,
                amount=data.amount,
                target_date=data.target_date,
            )
        )

    async def delete_goal(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        goal = await self._repo.get_by_category(user_id, category_id)
        if goal is None:
            raise NotFoundError("Цели по этой категории нет.")
        await self._repo.delete(goal)

    async def progress(
        self,
        user_id: uuid.UUID,
        month: date,
        budgets: list[BudgetRead],
    ) -> list[GoalProgress]:
        """Расчёт по всем целям на указанный месяц."""
        by_category = {b.category_id: b for b in budgets}
        return [
            _progress(goal, month, by_category.get(goal.category_id))
            for goal in await self._repo.list_all(user_id)
        ]


def _progress(
    goal: CategoryGoal, month: date, budget: BudgetRead | None
) -> GoalProgress:
    planned = budget.planned if budget is not None else Decimal(0)

    if goal.kind == GoalKind.MONTHLY:
        # Ежемесячная цель ничего не копит: нужна сумма в этом
        # месяце, и накопленное прошлых месяцев к ней отношения не
        # имеет.
        need = goal.amount
        return GoalProgress(
            goal=goal,
            accumulated=planned,
            need_this_month=need,
            planned_this_month=planned,
            still_to_add=max(Decimal(0), need - planned),
            months_left=1,
            is_reached=planned >= need,
        )

    # Цель к дате. Накоплено — то, что лежит в конверте без плана
    # текущего месяца: план мы как раз и собираемся назначить.
    accumulated = Decimal(0)
    if budget is not None:
        accumulated = budget.rollover_amount - budget.spent

    target = goal.target_date or month
    months_left = months_between(month, target)
    left = goal.amount - accumulated
    if left <= 0:
        return GoalProgress(
            goal=goal,
            accumulated=accumulated,
            need_this_month=Decimal(0),
            planned_this_month=planned,
            still_to_add=Decimal(0),
            months_left=months_left,
            is_reached=True,
        )

    need = (left / months_left).quantize(_CENT, rounding=ROUND_CEILING)
    return GoalProgress(
        goal=goal,
        accumulated=accumulated,
        need_this_month=need,
        planned_this_month=planned,
        still_to_add=max(Decimal(0), need - planned),
        months_left=months_left,
        is_reached=False,
    )
