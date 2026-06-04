"""Юнит-тесты RecurringService на фейковых репозиториях.

Покрывают CRUD, запекание amount_rub (RUB и кросс-валюта),
валидацию категории (только активная расходная), архивирование и
generate_from_categories (оценка из истории, пропуск существующих и
нерасходных категорий).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums import CategoryKind, RequiredKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.categories.models import Category
from app.domains.recurring.models import RecurringExpense
from app.domains.recurring.schemas import (
    RecurringCreate,
    RecurringUpdate,
)
from app.domains.recurring.service import RecurringService

USER = uuid.uuid4()


class FakeRecurringRepo:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, RecurringExpense] = {}
        # category_id -> сумма обязательных расходов за окно (со знаком)
        self.spend: dict[uuid.UUID, Decimal] = {}

    async def list_active(self, user_id):
        return [
            i
            for i in self.items.values()
            if i.user_id == user_id and not i.is_archived
        ]

    async def get(self, recurring_id, user_id):
        i = self.items.get(recurring_id)
        if i is None or i.user_id != user_id:
            return None
        return i

    async def add(self, item):
        if item.id is None:
            item.id = uuid.uuid4()
        now = datetime.now(UTC)
        if item.created_at is None:
            item.created_at = now
        if item.updated_at is None:
            item.updated_at = now
        if item.is_archived is None:
            item.is_archived = False
        self.items[item.id] = item
        return item

    async def required_spend_by_category(self, user_id, date_from, date_to):
        return dict(self.spend)


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


class FakeCurrencies:
    def __init__(self, rates: dict[str, Decimal] | None = None) -> None:
        self._rates = rates or {}

    def _rate(self, code: str) -> Decimal:
        if code == "RUB":
            return Decimal(1)
        if code not in self._rates:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return self._rates[code]

    async def convert(self, amount, from_code, to_code):
        if from_code == to_code:
            return amount
        rub = amount * self._rate(from_code)
        if to_code == "RUB":
            return rub
        return rub / self._rate(to_code)


def _category(
    name: str = "Аренда",
    kind: CategoryKind = CategoryKind.EXPENSE,
    archived: bool = False,
) -> Category:
    cat = Category(
        user_id=USER,
        name=name,
        kind=kind,
        parent_id=None,
        sort_order=0,
    )
    cat.id = uuid.uuid4()
    cat.is_archived = archived
    return cat


def _service(
    repo: FakeRecurringRepo,
    categories: list[Category] | None = None,
    rates: dict[str, Decimal] | None = None,
) -> RecurringService:
    return RecurringService(
        repo, FakeCategoryRepo(categories or []), FakeCurrencies(rates)
    )


def _create(category_id, **over) -> RecurringCreate:
    base = {
        "category_id": category_id,
        "name": "Аренда",
        "monthly_amount": Decimal("30000"),
    }
    base.update(over)
    return RecurringCreate(**base)


async def test_create_rub_bakes_amount() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat])
    item = await svc.create_recurring(USER, _create(cat.id))
    assert item.amount_rub == Decimal("30000")
    assert item.currency_code == "RUB"
    assert item.required == RequiredKind.REQUIRED


async def test_create_foreign_currency_bakes_rub() -> None:
    repo = FakeRecurringRepo()
    cat = _category(name="Подписки")
    svc = _service(repo, [cat], rates={"USD": Decimal("90")})
    item = await svc.create_recurring(
        USER,
        _create(cat.id, monthly_amount=Decimal("50"), currency_code="usd"),
    )
    assert item.currency_code == "USD"
    assert item.amount_rub == Decimal("4500")


async def test_create_missing_category() -> None:
    repo = FakeRecurringRepo()
    svc = _service(repo, [])
    with pytest.raises(NotFoundError):
        await svc.create_recurring(USER, _create(uuid.uuid4()))


async def test_create_income_category_rejected() -> None:
    repo = FakeRecurringRepo()
    cat = _category(kind=CategoryKind.INCOME)
    svc = _service(repo, [cat])
    with pytest.raises(ValidationFailedError):
        await svc.create_recurring(USER, _create(cat.id))


async def test_create_archived_category_rejected() -> None:
    repo = FakeRecurringRepo()
    cat = _category(archived=True)
    svc = _service(repo, [cat])
    with pytest.raises(ValidationFailedError):
        await svc.create_recurring(USER, _create(cat.id))


async def test_create_unknown_currency_rejected() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat])
    with pytest.raises(NotFoundError):
        await svc.create_recurring(USER, _create(cat.id, currency_code="GBP"))


async def test_update_amount_recomputes_rub() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat], rates={"USD": Decimal("90")})
    item = await svc.create_recurring(
        USER,
        _create(cat.id, monthly_amount=Decimal("50"), currency_code="USD"),
    )
    updated = await svc.update_recurring(
        item.id, USER, RecurringUpdate(monthly_amount=Decimal("60"))
    )
    assert updated.monthly_amount == Decimal("60")
    assert updated.amount_rub == Decimal("5400")


async def test_update_name_keeps_amount() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat])
    item = await svc.create_recurring(USER, _create(cat.id))
    updated = await svc.update_recurring(
        item.id, USER, RecurringUpdate(name="Квартира")
    )
    assert updated.name == "Квартира"
    assert updated.amount_rub == Decimal("30000")


async def test_update_missing() -> None:
    repo = FakeRecurringRepo()
    svc = _service(repo, [])
    with pytest.raises(NotFoundError):
        await svc.update_recurring(
            uuid.uuid4(), USER, RecurringUpdate(name="X")
        )


async def test_archive_hides_from_list() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat])
    item = await svc.create_recurring(USER, _create(cat.id))
    await svc.archive_recurring(item.id, USER)
    assert item.is_archived is True
    assert await svc.list_recurring(USER) == []


async def test_generate_estimates_skips_existing_and_income() -> None:
    repo = FakeRecurringRepo()
    cat_rent = _category(name="Аренда")
    cat_food = _category(name="Еда")
    cat_income = _category(name="Зарплата", kind=CategoryKind.INCOME)
    svc = _service(repo, [cat_rent, cat_food, cat_income])
    # по «Еда» уже есть активный план — пропустить
    await repo.add(
        RecurringExpense(
            user_id=USER,
            required=RequiredKind.REQUIRED,
            category_id=cat_food.id,
            name="Еда",
            monthly_amount=Decimal("100"),
            currency_code="RUB",
            amount_rub=Decimal("100"),
        )
    )
    # обязательные расходы за 3 месяца (со знаком)
    repo.spend = {
        cat_rent.id: Decimal("-90000"),
        cat_food.id: Decimal("-30000"),
        cat_income.id: Decimal("-5000"),
    }
    created = await svc.generate_from_categories(USER)
    assert len(created) == 1
    item = created[0]
    assert item.category_id == cat_rent.id
    assert item.name == "Аренда"
    assert item.monthly_amount == Decimal("30000.00")  # 90000 / 3
    assert item.amount_rub == Decimal("30000.00")
    assert item.currency_code == "RUB"
    assert item.required == RequiredKind.REQUIRED


async def test_generate_rounds_estimate() -> None:
    repo = FakeRecurringRepo()
    cat = _category(name="Связь")
    svc = _service(repo, [cat])
    repo.spend = {cat.id: Decimal("-100000")}  # /3 = 33333.3333...
    created = await svc.generate_from_categories(USER)
    assert created[0].monthly_amount == Decimal("33333.33")


async def test_list_returns_only_active() -> None:
    repo = FakeRecurringRepo()
    cat = _category()
    svc = _service(repo, [cat])
    keep = await svc.create_recurring(USER, _create(cat.id, name="A"))
    gone = await svc.create_recurring(USER, _create(cat.id, name="B"))
    await svc.archive_recurring(gone.id, USER)
    items = await svc.list_recurring(USER)
    assert [i.id for i in items] == [keep.id]
