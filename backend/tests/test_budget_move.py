"""Перенос плана между категориями — третье правило ВНБ.

«Держите удар»: вылезли за лимит — некайтесь, а возьмите из другой
категории. Без этого перерасход только копится красным, а метод
держится на том, что план можно пересобрать по ходу месяца.
"""

import uuid
from decimal import Decimal

import pytest

from app.core.enums import CategoryKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.budgets.service import BudgetService

MONTH = "2026-08"


class _Budget:
    def __init__(self, category_id: uuid.UUID, planned: Decimal) -> None:
        self.id = uuid.uuid4()
        self.category_id = category_id
        self.planned = planned
        self.rollover = False
        self.notes = None


class _Repo:
    def __init__(self, budgets: list[_Budget]) -> None:
        self.budgets = budgets
        self.added: list[_Budget] = []

    async def get_by_month_category(
        self, user_id: uuid.UUID, month: object, category_id: uuid.UUID
    ) -> _Budget | None:
        for budget in self.budgets:
            if budget.category_id == category_id:
                return budget
        return None

    async def add(self, budget: object) -> object:
        self.added.append(budget)  # type: ignore[arg-type]
        return budget


class _Category:
    def __init__(self) -> None:
        self.is_archived = False
        self.kind = CategoryKind.EXPENSE


class _Categories:
    def __init__(self, known: set[uuid.UUID]) -> None:
        self._known = known

    async def get(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> _Category | None:
        return _Category() if category_id in self._known else None


FOOD = uuid.uuid4()
FUN = uuid.uuid4()


def _service(budgets: list[_Budget]) -> tuple[BudgetService, _Repo]:
    repo = _Repo(budgets)
    from typing import Any, cast

    service = BudgetService(
        cast(Any, repo), cast(Any, _Categories({FOOD, FUN}))
    )
    return service, repo


async def test_move_shifts_planned_between_categories() -> None:
    food = _Budget(FOOD, Decimal("10000"))
    fun = _Budget(FUN, Decimal("5000"))
    service, _ = _service([food, fun])

    await service.move_planned(
        uuid.uuid4(),
        month=MONTH,
        from_category_id=FUN,
        to_category_id=FOOD,
        amount=Decimal("1500"),
    )

    assert fun.planned == Decimal("3500")
    assert food.planned == Decimal("11500")


async def test_total_planned_is_unchanged() -> None:
    """Перенос не создаёт денег — только меняет их назначение."""
    food = _Budget(FOOD, Decimal("10000"))
    fun = _Budget(FUN, Decimal("5000"))
    service, _ = _service([food, fun])
    before = food.planned + fun.planned

    await service.move_planned(
        uuid.uuid4(),
        month=MONTH,
        from_category_id=FUN,
        to_category_id=FOOD,
        amount=Decimal("2000"),
    )
    assert food.planned + fun.planned == before


async def test_cannot_move_more_than_planned() -> None:
    fun = _Budget(FUN, Decimal("5000"))
    service, _ = _service([_Budget(FOOD, Decimal("10000")), fun])

    with pytest.raises(ValidationFailedError):
        await service.move_planned(
            uuid.uuid4(),
            month=MONTH,
            from_category_id=FUN,
            to_category_id=FOOD,
            amount=Decimal("5000.01"),
        )
    assert fun.planned == Decimal("5000")


async def test_amount_must_be_positive() -> None:
    service, _ = _service(
        [_Budget(FOOD, Decimal("10000")), _Budget(FUN, Decimal("5000"))]
    )
    for bad in (Decimal("0"), Decimal("-100")):
        with pytest.raises(ValidationFailedError):
            await service.move_planned(
                uuid.uuid4(),
                month=MONTH,
                from_category_id=FUN,
                to_category_id=FOOD,
                amount=bad,
            )


async def test_cannot_move_into_the_same_category() -> None:
    service, _ = _service([_Budget(FOOD, Decimal("10000"))])
    with pytest.raises(ValidationFailedError):
        await service.move_planned(
            uuid.uuid4(),
            month=MONTH,
            from_category_id=FOOD,
            to_category_id=FOOD,
            amount=Decimal("100"),
        )


async def test_source_without_a_plan_is_rejected() -> None:
    """Взять из категории, где плана нет, нельзя."""
    service, _ = _service([_Budget(FOOD, Decimal("10000"))])
    with pytest.raises(ValidationFailedError):
        await service.move_planned(
            uuid.uuid4(),
            month=MONTH,
            from_category_id=FUN,
            to_category_id=FOOD,
            amount=Decimal("100"),
        )


async def test_target_without_a_plan_gets_one() -> None:
    """Принимающая категория могла быть без плана — заводим его."""
    fun = _Budget(FUN, Decimal("5000"))
    service, repo = _service([fun])

    await service.move_planned(
        uuid.uuid4(),
        month=MONTH,
        from_category_id=FUN,
        to_category_id=FOOD,
        amount=Decimal("1200"),
    )

    assert fun.planned == Decimal("3800")
    assert len(repo.added) == 1
    assert repo.added[0].planned == Decimal("1200")


async def test_unknown_category_is_rejected() -> None:
    service, _ = _service([_Budget(FOOD, Decimal("10000"))])
    with pytest.raises(NotFoundError):
        await service.move_planned(
            uuid.uuid4(),
            month=MONTH,
            from_category_id=FOOD,
            to_category_id=uuid.uuid4(),
            amount=Decimal("100"),
        )
