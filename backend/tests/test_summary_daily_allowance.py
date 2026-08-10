"""Сколько можно тратить в день до конца горизонта.

Правило «истинных расходов» из ВНБ: деньги на счету — не те же
деньги, что можно потратить. Сначала из остатка вычитаются
обязательства, которые точно наступят, и только остаток делится
на дни.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from app.core.exceptions import NotFoundError
from app.domains.summary.service import SummaryService


class _Account:
    def __init__(self, name: str, currency: str, initial: Decimal) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.currency_code = currency
        self.initial_balance = initial


class _Credit:
    def __init__(
        self,
        balance: Decimal,
        monthly_payment: Decimal | None = None,
        payment_day: int | None = None,
        currency: str = "RUB",
    ) -> None:
        self.currency_code = currency
        self.principal_balance = balance
        self.monthly_payment = monthly_payment
        self.payment_day = payment_day


class _Recurring:
    def __init__(self, name: str, amount_rub: Decimal) -> None:
        self.category_id = uuid.uuid4()
        self.name = name
        self.amount_rub = amount_rub


class _Budget:
    def __init__(self, category_id: uuid.UUID, planned: Decimal) -> None:
        self.category_id = category_id
        self.planned = planned


class _Repo:
    def __init__(
        self,
        accounts: list[_Account],
        credits: list[_Credit],
        recurring: list[_Recurring],
        spent: dict[uuid.UUID, Decimal] | None = None,
        budgets: list[_Budget] | None = None,
    ) -> None:
        self._accounts = accounts
        self._credits = credits
        self._recurring = recurring
        self._spent = spent or {}
        self._budgets = budgets or []

    async def budgets_for_month(
        self, user_id: uuid.UUID, month: date
    ) -> list[Any]:
        return list(self._budgets)

    async def active_accounts(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._accounts)

    async def balances_by_account(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, Decimal]:
        return {}

    async def active_credits(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._credits)

    async def active_recurring(self, user_id: uuid.UUID) -> list[Any]:
        return list(self._recurring)

    async def spending_by_category(
        self,
        user_id: uuid.UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[tuple[uuid.UUID | None, Decimal]]:
        return list(self._spent.items())


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        rates = {"RUB": Decimal(1), "UZS": Decimal("0.0072")}
        if code not in rates:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return rates[code]


def _service(
    accounts: list[_Account],
    credits: list[_Credit] | None = None,
    recurring: list[_Recurring] | None = None,
    spent: dict[uuid.UUID, Decimal] | None = None,
    budgets: list[_Budget] | None = None,
) -> SummaryService:
    return SummaryService(
        cast(
            Any,
            _Repo(accounts, credits or [], recurring or [], spent, budgets),
        ),
        cast(Any, _Currencies()),
    )


_NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


async def test_plain_split_over_remaining_days() -> None:
    """Никаких обязательств: 60 000 на 22 дня августа."""
    service = _service([_Account("Альфа", "RUB", Decimal("60000"))])
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.until == date(2026, 8, 31)
    assert result.days_left == 22
    assert result.liquid_rub == Decimal("60000")
    assert result.safe_to_spend_rub == Decimal("60000")
    assert result.per_day_rub == Decimal("2727.27")


async def test_recurring_obligations_are_reserved_first() -> None:
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        recurring=[
            _Recurring("Аренда", Decimal("19500")),
            _Recurring("Подписки", Decimal("15000")),
        ],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("34500")
    assert result.safe_to_spend_rub == Decimal("25500")
    assert [o.name for o in result.obligations] == ["Аренда", "Подписки"]


async def test_already_paid_part_of_recurring_is_not_reserved_twice() -> None:
    """Аренду уже заплатили — резервировать её второй раз незачем."""
    rent = _Recurring("Аренда", Decimal("19500"))
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        recurring=[rent],
        spent={rent.category_id: Decimal("-19500")},
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("0")
    assert result.safe_to_spend_rub == Decimal("60000")


async def test_overspent_recurring_does_not_become_a_bonus() -> None:
    """Потратили больше плана — это не освобождает деньги."""
    rent = _Recurring("Аренда", Decimal("19500"))
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        recurring=[rent],
        spent={rent.category_id: Decimal("-25000")},
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("0")


async def test_upcoming_credit_payment_is_reserved() -> None:
    """Платёж 20-го числа наступит до конца месяца."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        credits=[
            _Credit(
                Decimal("280650.24"),
                monthly_payment=Decimal("10700"),
                payment_day=20,
            )
        ],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("10700")
    assert result.safe_to_spend_rub == Decimal("49300")


async def test_credit_payment_already_past_is_not_reserved() -> None:
    """Платёж 4-го числа уже прошёл — резервировать нечего."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        credits=[
            _Credit(
                Decimal("280650.24"),
                monthly_payment=Decimal("10700"),
                payment_day=4,
            )
        ],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("0")


async def test_horizon_can_reach_into_next_month() -> None:
    """До 9 сентября попадают оба платежа по кредиту."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        credits=[
            _Credit(
                Decimal("280650.24"),
                monthly_payment=Decimal("10700"),
                payment_day=20,
            )
        ],
    )
    result = await service.daily_allowance(
        uuid.uuid4(),
        "Europe/Moscow",
        until=date(2026, 9, 30),
        now=_NOW,
    )
    assert result.obligations_rub == Decimal("21400")


async def test_obligations_beyond_the_money_give_zero_per_day() -> None:
    """Отрицательный дневной лимит — бессмысленная цифра."""
    service = _service(
        [_Account("Альфа", "RUB", Decimal("10000"))],
        recurring=[_Recurring("Аренда", Decimal("19500"))],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.safe_to_spend_rub == Decimal("-9500")
    assert result.per_day_rub == Decimal("0")
    assert result.is_short is True


async def test_foreign_accounts_are_converted() -> None:
    service = _service(
        [
            _Account("Альфа", "RUB", Decimal("1000")),
            _Account("Uzcard", "UZS", Decimal("100000")),
        ]
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.liquid_rub == Decimal("1720.0000")


async def test_last_day_of_month_still_gives_a_day() -> None:
    """Делить на ноль дней нельзя, а 31-е — тоже день."""
    service = _service([_Account("Альфа", "RUB", Decimal("3100"))])
    result = await service.daily_allowance(
        uuid.uuid4(),
        "Europe/Moscow",
        now=datetime(2026, 8, 31, 9, 0, tzinfo=UTC),
    )
    assert result.days_left == 1
    assert result.per_day_rub == Decimal("3100.00")


async def test_past_horizon_is_rejected() -> None:
    service = _service([_Account("Альфа", "RUB", Decimal("1000"))])
    result = await service.daily_allowance(
        uuid.uuid4(),
        "Europe/Moscow",
        until=date(2026, 8, 1),
        now=_NOW,
    )
    # Горизонт в прошлом — считаем по сегодняшний день, не падаем.
    assert result.days_left == 1


async def test_unallocated_subtracts_category_plans() -> None:
    """Первое правило: свободны только нераспланированные деньги."""
    food = uuid.uuid4()
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        budgets=[_Budget(food, Decimal("20000"))],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    # Планы не трогают дневной лимит: это не обязательства.
    assert result.safe_to_spend_rub == Decimal("60000")
    assert result.planned_remaining_rub == Decimal("20000")
    assert result.unallocated_rub == Decimal("40000")


async def test_plan_and_recurring_on_one_category_count_once() -> None:
    """План и план-минимум по одной категории — не двойной резерв."""
    rent_category = uuid.uuid4()
    rent = _Recurring("Аренда", Decimal("19500"))
    rent.category_id = rent_category
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        recurring=[rent],
        budgets=[_Budget(rent_category, Decimal("19500"))],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.obligations_rub == Decimal("19500")
    assert result.unallocated_rub == Decimal("40500")


async def test_bigger_of_plan_and_recurring_wins() -> None:
    """Аренда выросла — резервируем большее из двух, а не сумму."""
    rent_category = uuid.uuid4()
    rent = _Recurring("Аренда", Decimal("19500"))
    rent.category_id = rent_category
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        recurring=[rent],
        budgets=[_Budget(rent_category, Decimal("21000"))],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.unallocated_rub == Decimal("39000")


async def test_spent_plan_frees_the_money() -> None:
    food = uuid.uuid4()
    service = _service(
        [_Account("Альфа", "RUB", Decimal("60000"))],
        budgets=[_Budget(food, Decimal("20000"))],
        spent={food: Decimal("-20000")},
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.planned_remaining_rub == Decimal("0")
    assert result.unallocated_rub == Decimal("60000")


async def test_overplanned_month_shows_negative_unallocated() -> None:
    """Распланировано больше, чем есть, — это надо видеть."""
    food = uuid.uuid4()
    service = _service(
        [_Account("Альфа", "RUB", Decimal("10000"))],
        budgets=[_Budget(food, Decimal("30000"))],
    )
    result = await service.daily_allowance(
        uuid.uuid4(), "Europe/Moscow", now=_NOW
    )
    assert result.unallocated_rub == Decimal("-20000")
    assert result.is_overplanned is True
