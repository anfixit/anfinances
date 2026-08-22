"""Цели по категориям: сколько положить в конверт в этом месяце.

Здесь одна формула, и вся её ценность — в честности. Считать от нуля,
когда в конверте уже лежит половина, значит врать; после пары таких
подсказок цели перестают читать.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.enums import GoalKind
from app.core.exceptions import NotFoundError
from app.domains.budgets.schemas import BudgetRead
from app.domains.goals.models import CategoryGoal
from app.domains.goals.schemas import GoalUpsert
from app.domains.goals.service import GoalService, months_between

USER = uuid.uuid4()
CATEGORY = uuid.uuid4()
MONTH = date(2026, 8, 1)
NOW = datetime(2026, 8, 1)


class _Repo:
    def __init__(self, goals: list[CategoryGoal] | None = None) -> None:
        self.goals = goals or []

    async def list_all(self, user_id: uuid.UUID) -> list[CategoryGoal]:
        return list(self.goals)

    async def get_by_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> CategoryGoal | None:
        for goal in self.goals:
            if goal.category_id == category_id:
                return goal
        return None

    async def add(self, goal: CategoryGoal) -> CategoryGoal:
        goal.created_at = NOW
        goal.updated_at = NOW
        self.goals.append(goal)
        return goal

    async def delete(self, goal: CategoryGoal) -> None:
        self.goals.remove(goal)


class _Categories:
    def __init__(self, exists: bool = True) -> None:
        self._exists = exists

    async def get(self, category_id: uuid.UUID, user_id: uuid.UUID) -> object:
        return object() if self._exists else None


def _goal(
    kind: GoalKind, amount: str, target: date | None = None
) -> CategoryGoal:
    goal = CategoryGoal(
        user_id=USER,
        category_id=CATEGORY,
        kind=kind,
        amount=Decimal(amount),
        target_date=target,
    )
    goal.id = uuid.uuid4()
    goal.created_at = NOW
    goal.updated_at = NOW
    return goal


def _budget(
    planned: str = "0", rollover_amount: str = "0", spent: str = "0"
) -> BudgetRead:
    available = Decimal(planned) + Decimal(rollover_amount)
    return BudgetRead(
        id=uuid.uuid4(),
        month="2026-08",
        category_id=CATEGORY,
        planned=Decimal(planned),
        notes=None,
        rollover=True,
        rollover_amount=Decimal(rollover_amount),
        available=available,
        spent=Decimal(spent),
        remaining=available - Decimal(spent),
        created_at=NOW,
        updated_at=NOW,
    )


def _service(goals: list[CategoryGoal], exists: bool = True) -> GoalService:
    return GoalService(_Repo(goals), _Categories(exists))  # type: ignore[arg-type]


def test_months_counts_the_current_one() -> None:
    """До первого декабря из августа — пять месяцев, включая август."""
    assert months_between(date(2026, 8, 1), date(2026, 12, 1)) == 5


def test_past_target_needs_everything_now() -> None:
    """Отрицательный делитель дал бы отрицательный взнос."""
    assert months_between(date(2026, 8, 1), date(2026, 5, 1)) == 1


async def test_goal_by_date_splits_the_remainder() -> None:
    service = _service([_goal(GoalKind.BY_DATE, "60000", date(2026, 12, 1))])
    rows = await service.progress(USER, MONTH, [_budget()])
    assert rows[0].months_left == 5
    assert rows[0].need_this_month == Decimal("12000")


async def test_already_saved_lowers_the_instalment() -> None:
    """В конверте 40 000 из 60 000 — взнос должен упасть, а не стоять."""
    service = _service([_goal(GoalKind.BY_DATE, "60000", date(2026, 12, 1))])
    rows = await service.progress(
        USER, MONTH, [_budget(rollover_amount="40000")]
    )
    assert rows[0].accumulated == Decimal("40000")
    assert rows[0].need_this_month == Decimal("4000")


async def test_spending_from_the_envelope_raises_it_back() -> None:
    """Потратили из копилки — доложить придётся больше."""
    service = _service([_goal(GoalKind.BY_DATE, "60000", date(2026, 12, 1))])
    rows = await service.progress(
        USER, MONTH, [_budget(rollover_amount="40000", spent="10000")]
    )
    assert rows[0].accumulated == Decimal("30000")
    assert rows[0].need_this_month == Decimal("6000")


async def test_reached_goal_asks_for_nothing() -> None:
    service = _service([_goal(GoalKind.BY_DATE, "60000", date(2026, 12, 1))])
    rows = await service.progress(
        USER, MONTH, [_budget(rollover_amount="60000")]
    )
    assert rows[0].is_reached is True
    assert rows[0].need_this_month == Decimal(0)


async def test_instalment_is_rounded_up() -> None:
    """По 3 333,33 семь раз — до цели не хватит копейки."""
    service = _service([_goal(GoalKind.BY_DATE, "10000", date(2026, 10, 1))])
    rows = await service.progress(USER, MONTH, [_budget()])
    assert rows[0].months_left == 3
    assert rows[0].need_this_month == Decimal("3333.34")


async def test_monthly_goal_ignores_what_was_saved_before() -> None:
    """Аренда нужна каждый месяц целиком, прошлые взносы не в счёт."""
    service = _service([_goal(GoalKind.MONTHLY, "19500")])
    rows = await service.progress(
        USER, MONTH, [_budget(rollover_amount="100000")]
    )
    assert rows[0].need_this_month == Decimal("19500")
    assert rows[0].still_to_add == Decimal("19500")


async def test_already_planned_reduces_what_is_left_to_add() -> None:
    service = _service([_goal(GoalKind.MONTHLY, "19500")])
    rows = await service.progress(USER, MONTH, [_budget(planned="12000")])
    assert rows[0].still_to_add == Decimal("7500")
    assert rows[0].is_reached is False


async def test_goal_without_a_budget_line_still_computes() -> None:
    """Цель ставят до того, как заведут конверт."""
    service = _service([_goal(GoalKind.BY_DATE, "5000", date(2026, 9, 1))])
    rows = await service.progress(USER, MONTH, [])
    assert rows[0].accumulated == Decimal(0)
    assert rows[0].need_this_month == Decimal("2500")


async def test_goal_on_a_missing_category_is_refused() -> None:
    service = _service([], exists=False)
    with pytest.raises(NotFoundError):
        await service.upsert_goal(
            USER,
            GoalUpsert(
                category_id=CATEGORY,
                kind=GoalKind.MONTHLY,
                amount=Decimal("100"),
            ),
        )


async def test_second_goal_replaces_the_first() -> None:
    """Две цели на один конверт — два ответа на один вопрос."""
    goals = [_goal(GoalKind.MONTHLY, "100")]
    service = _service(goals)
    await service.upsert_goal(
        USER,
        GoalUpsert(
            category_id=CATEGORY,
            kind=GoalKind.BY_DATE,
            amount=Decimal("60000"),
            target_date=date(2026, 12, 1),
        ),
    )
    assert len(goals) == 1
    assert goals[0].kind == GoalKind.BY_DATE


def test_by_date_goal_requires_a_date() -> None:
    with pytest.raises(ValueError, match="дата"):
        GoalUpsert(
            category_id=CATEGORY,
            kind=GoalKind.BY_DATE,
            amount=Decimal("100"),
        )


def test_monthly_goal_refuses_a_date() -> None:
    """Дата у ежемесячной цели ничего не значит и только путала бы."""
    with pytest.raises(ValueError, match="даты"):
        GoalUpsert(
            category_id=CATEGORY,
            kind=GoalKind.MONTHLY,
            amount=Decimal("100"),
            target_date=date(2026, 12, 1),
        )
