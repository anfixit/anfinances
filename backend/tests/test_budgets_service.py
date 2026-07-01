"""Юнит-тесты BudgetService на фейковых репозиториях.

Проверяют логику переноса остатка (rollover): отсутствие переноса,
накопление, освобождение за счёт экономии, перерасход в минус,
перенос через пропущенный месяц, а также валидацию категории,
создание/обновление/удаление и upsert при импорте.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.enums import CategoryKind
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.budgets.models import Budget
from app.domains.budgets.schemas import (
    BudgetCreate,
    BudgetImport,
    BudgetImportItem,
    BudgetUpdate,
)
from app.domains.budgets.service import BudgetService
from app.domains.categories.models import Category

USER = uuid.uuid4()


class FakeBudgetRepo:
    """In-memory бюджеты + расходные транзакции для агрегатов."""

    def __init__(self) -> None:
        self.budgets: dict[uuid.UUID, Budget] = {}
        # (category_id, date, amount_rub); расход хранится amount_rub < 0
        self.txs: list[tuple[uuid.UUID, datetime, Decimal]] = []

    async def list_by_month(self, user_id, month):
        return [
            b
            for b in self.budgets.values()
            if b.user_id == user_id and b.month == month
        ]

    async def get(self, budget_id, user_id):
        b = self.budgets.get(budget_id)
        if b is None or b.user_id != user_id:
            return None
        return b

    async def get_by_month_category(self, user_id, month, category_id):
        for b in self.budgets.values():
            if (
                b.user_id == user_id
                and b.month == month
                and b.category_id == category_id
            ):
                return b
        return None

    async def add(self, budget):
        if budget.id is None:
            budget.id = uuid.uuid4()
        now = datetime.now(UTC)
        if budget.created_at is None:
            budget.created_at = now
        if budget.updated_at is None:
            budget.updated_at = now
        self.budgets[budget.id] = budget
        return budget

    async def delete(self, budget):
        self.budgets.pop(budget.id, None)

    async def spent_by_category(self, user_id, date_from, date_to):
        out: dict[uuid.UUID, Decimal] = {}
        for cat, when, amount in self.txs:
            if date_from <= when <= date_to:
                out[cat] = out.get(cat, Decimal(0)) + amount
        return out

    async def planned_before(self, user_id, month):
        out: dict[uuid.UUID, Decimal] = {}
        for b in self.budgets.values():
            if b.user_id == user_id and b.month < month:
                out[b.category_id] = (
                    out.get(b.category_id, Decimal(0)) + b.planned
                )
        return out

    async def spent_before(self, user_id, before):
        out: dict[uuid.UUID, Decimal] = {}
        for cat, when, amount in self.txs:
            if when < before:
                out[cat] = out.get(cat, Decimal(0)) + amount
        return out


class FakeCategoryRepo:
    def __init__(self, categories: list[Category]) -> None:
        self.items = {c.id: c for c in categories}

    async def get(self, category_id, user_id):
        c = self.items.get(category_id)
        if c is None or c.user_id != user_id:
            return None
        return c

    async def list_active(self, user_id):
        return [c for c in self.items.values() if not c.is_archived]

    async def get_active_sibling(self, user_id, parent_id, name):
        return None

    async def has_children(self, category_id):
        return False

    async def add(self, category):
        return category


def _category(
    kind: CategoryKind = CategoryKind.EXPENSE,
    archived: bool = False,
    parent_id: uuid.UUID | None = None,
) -> Category:
    cat = Category(
        user_id=USER,
        name="Развлечения",
        kind=kind,
        parent_id=parent_id,
        sort_order=0,
    )
    cat.id = uuid.uuid4()
    cat.is_archived = archived
    return cat


def _service(
    repo: FakeBudgetRepo,
    categories: list[Category] | None = None,
) -> BudgetService:
    return BudgetService(repo, FakeCategoryRepo(categories or []))


def _budget(
    repo: FakeBudgetRepo,
    category_id: uuid.UUID,
    month: str,
    planned: str,
    rollover: bool,
) -> Budget:
    year, mon = month.split("-")
    budget = Budget(
        user_id=USER,
        month=date(int(year), int(mon), 1),
        category_id=category_id,
        planned=Decimal(planned),
        rollover=rollover,
        notes=None,
    )
    budget.id = uuid.uuid4()
    now = datetime.now(UTC)
    budget.created_at = now
    budget.updated_at = now
    repo.budgets[budget.id] = budget
    return budget


def _spend(category_id: uuid.UUID, month: str, amount: str):
    """Расход на сумму amount (положит. модуль) в указанном месяце."""
    year, mon = month.split("-")
    when = datetime(int(year), int(mon), 15, tzinfo=UTC)
    return (category_id, when, -Decimal(amount))


async def test_no_rollover_spent_and_remaining() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    _budget(repo, cat.id, "2026-01", "1000", rollover=False)
    repo.txs.append(_spend(cat.id, "2026-01", "300"))
    svc = _service(repo, [cat])
    [view] = await svc.list_budgets(USER, "2026-01")
    assert view.spent == Decimal("300")
    assert view.rollover_amount == Decimal("0")
    assert view.available == Decimal("1000")
    assert view.remaining == Decimal("700")


async def test_parent_budget_includes_child_spending() -> None:
    repo = FakeBudgetRepo()
    parent = _category()
    child = _category(parent_id=parent.id)
    _budget(repo, parent.id, "2026-01", "1000", rollover=False)
    repo.txs.append(_spend(parent.id, "2026-01", "100"))
    repo.txs.append(_spend(child.id, "2026-01", "300"))
    svc = _service(repo, [parent, child])

    [view] = await svc.list_budgets(USER, "2026-01")

    assert view.spent == Decimal("400")
    assert view.remaining == Decimal("600")


async def test_child_budget_does_not_include_parent_spending() -> None:
    repo = FakeBudgetRepo()
    parent = _category()
    child = _category(parent_id=parent.id)
    _budget(repo, child.id, "2026-01", "1000", rollover=False)
    repo.txs.append(_spend(parent.id, "2026-01", "100"))
    repo.txs.append(_spend(child.id, "2026-01", "300"))
    svc = _service(repo, [parent, child])

    [view] = await svc.list_budgets(USER, "2026-01")

    assert view.spent == Decimal("300")
    assert view.remaining == Decimal("700")


async def test_parent_rollover_includes_child_spending() -> None:
    repo = FakeBudgetRepo()
    parent = _category()
    child = _category(parent_id=parent.id)
    _budget(repo, parent.id, "2026-01", "1000", rollover=True)
    _budget(repo, parent.id, "2026-02", "1000", rollover=True)
    repo.txs.append(_spend(child.id, "2026-01", "300"))
    svc = _service(repo, [parent, child])

    [view] = await svc.list_budgets(USER, "2026-02")

    assert view.rollover_amount == Decimal("700")
    assert view.available == Decimal("1700")


async def test_rollover_accumulation() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    for month in ("2026-01", "2026-02", "2026-03"):
        _budget(repo, cat.id, month, "1000", rollover=True)
    svc = _service(repo, [cat])
    [march] = await svc.list_budgets(USER, "2026-03")
    assert march.rollover_amount == Decimal("2000")
    assert march.available == Decimal("3000")
    assert march.spent == Decimal("0")
    assert march.remaining == Decimal("3000")


async def test_rollover_savings_frees_next_month() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    _budget(repo, cat.id, "2026-01", "5000", rollover=True)
    _budget(repo, cat.id, "2026-02", "5000", rollover=True)
    repo.txs.append(_spend(cat.id, "2026-01", "3000"))
    svc = _service(repo, [cat])
    [feb] = await svc.list_budgets(USER, "2026-02")
    assert feb.rollover_amount == Decimal("2000")
    assert feb.available == Decimal("7000")


async def test_rollover_overspend_goes_negative() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    _budget(repo, cat.id, "2026-01", "1000", rollover=True)
    _budget(repo, cat.id, "2026-02", "1000", rollover=True)
    repo.txs.append(_spend(cat.id, "2026-01", "1500"))
    svc = _service(repo, [cat])
    [feb] = await svc.list_budgets(USER, "2026-02")
    assert feb.rollover_amount == Decimal("-500")
    assert feb.available == Decimal("500")
    assert feb.remaining == Decimal("500")


async def test_rollover_survives_gap_with_spend() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    _budget(repo, cat.id, "2026-01", "1000", rollover=True)
    # февраль без строки бюджета, но был расход 400
    repo.txs.append(_spend(cat.id, "2026-02", "400"))
    _budget(repo, cat.id, "2026-03", "1000", rollover=True)
    svc = _service(repo, [cat])
    [march] = await svc.list_budgets(USER, "2026-03")
    # planned_before = 1000 (только январь), spent_before = 400
    assert march.rollover_amount == Decimal("600")
    assert march.available == Decimal("1600")


async def test_create_returns_enriched_view() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    svc = _service(repo, [cat])
    data = BudgetCreate(
        month="2026-01",
        category_id=cat.id,
        planned=Decimal("1000"),
        rollover=True,
    )
    view = await svc.create_budget(USER, data)
    assert view.month == "2026-01"
    assert view.planned == Decimal("1000")
    assert view.available == Decimal("1000")  # истории ещё нет
    assert len(repo.budgets) == 1


async def test_create_duplicate_rejected() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    _budget(repo, cat.id, "2026-01", "1000", rollover=False)
    svc = _service(repo, [cat])
    data = BudgetCreate(
        month="2026-01", category_id=cat.id, planned=Decimal("500")
    )
    with pytest.raises(AlreadyExistsError):
        await svc.create_budget(USER, data)


async def test_create_income_category_rejected() -> None:
    repo = FakeBudgetRepo()
    cat = _category(kind=CategoryKind.INCOME)
    svc = _service(repo, [cat])
    data = BudgetCreate(
        month="2026-01", category_id=cat.id, planned=Decimal("500")
    )
    with pytest.raises(ValidationFailedError):
        await svc.create_budget(USER, data)


async def test_create_archived_category_rejected() -> None:
    repo = FakeBudgetRepo()
    cat = _category(archived=True)
    svc = _service(repo, [cat])
    data = BudgetCreate(
        month="2026-01", category_id=cat.id, planned=Decimal("500")
    )
    with pytest.raises(ValidationFailedError):
        await svc.create_budget(USER, data)


async def test_create_missing_category_rejected() -> None:
    repo = FakeBudgetRepo()
    svc = _service(repo, [])
    data = BudgetCreate(
        month="2026-01", category_id=uuid.uuid4(), planned=Decimal("500")
    )
    with pytest.raises(NotFoundError):
        await svc.create_budget(USER, data)


async def test_update_planned() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    budget = _budget(repo, cat.id, "2026-01", "1000", rollover=False)
    svc = _service(repo, [cat])
    view = await svc.update_budget(
        budget.id, USER, BudgetUpdate(planned=Decimal("1500"))
    )
    assert view.planned == Decimal("1500")
    assert view.available == Decimal("1500")


async def test_update_missing_rejected() -> None:
    repo = FakeBudgetRepo()
    svc = _service(repo, [])
    with pytest.raises(NotFoundError):
        await svc.update_budget(
            uuid.uuid4(), USER, BudgetUpdate(planned=Decimal("1"))
        )


async def test_delete_removes_budget() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    budget = _budget(repo, cat.id, "2026-01", "1000", rollover=False)
    svc = _service(repo, [cat])
    await svc.delete_budget(budget.id, USER)
    assert repo.budgets == {}


async def test_import_upsert() -> None:
    repo = FakeBudgetRepo()
    cat_a = _category()
    cat_b = _category()
    _budget(repo, cat_a.id, "2026-01", "1000", rollover=False)
    svc = _service(repo, [cat_a, cat_b])
    data = BudgetImport(
        month="2026-01",
        items=[
            BudgetImportItem(category_id=cat_a.id, planned=Decimal("2000")),
            BudgetImportItem(category_id=cat_b.id, planned=Decimal("500")),
        ],
    )
    views = await svc.import_budgets(USER, data)
    assert len(views) == 2
    assert len(repo.budgets) == 2
    by_cat = {v.category_id: v for v in views}
    assert by_cat[cat_a.id].planned == Decimal("2000")  # обновлён
    assert by_cat[cat_b.id].planned == Decimal("500")  # создан


async def test_other_user_budget_not_visible() -> None:
    repo = FakeBudgetRepo()
    cat = _category()
    budget = _budget(repo, cat.id, "2026-01", "1000", rollover=False)
    budget.user_id = uuid.uuid4()  # чужой
    svc = _service(repo, [cat])
    assert await svc.list_budgets(USER, "2026-01") == []
