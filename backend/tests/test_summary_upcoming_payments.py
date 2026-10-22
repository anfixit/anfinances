"""Ближайшие платежи: что, когда и сколько.

Те же обязательства, что резервирует дневной лимит, но с датами и
в валюте платежа — для ассистента, который напоминает о платежах и
планирует погашение. Главные ловушки — концы месяцев (31-е в
феврале) и таймзона: «сегодня» считается по часам владельца.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from app.core.exceptions import NotFoundError
from app.domains.summary.service import SummaryService


class _Credit:
    def __init__(
        self,
        name: str,
        monthly_payment: Decimal | None,
        payment_day: int | None,
        currency: str = "RUB",
    ) -> None:
        self.name = name
        self.currency_code = currency
        self.principal_balance = Decimal("100000")
        self.monthly_payment = monthly_payment
        self.payment_day = payment_day


class _Recurring:
    def __init__(self, name: str, amount_rub: Decimal) -> None:
        self.category_id = uuid.uuid4()
        self.name = name
        self.amount_rub = amount_rub


class _Repo:
    def __init__(
        self,
        credits: list[_Credit],
        recurring: list[_Recurring],
        spent: dict[uuid.UUID, Decimal],
    ) -> None:
        self._credits = credits
        self._recurring = recurring
        self._spent = spent
        self.spending_periods: list[tuple[datetime, datetime]] = []

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
        self.spending_periods.append((date_from, date_to))
        return list(self._spent.items())


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        rates = {"RUB": Decimal(1), "UZS": Decimal("0.0072")}
        if code not in rates:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return rates[code]


def _service(
    credits: list[_Credit] | None = None,
    recurring: list[_Recurring] | None = None,
    spent: dict[uuid.UUID, Decimal] | None = None,
) -> tuple[SummaryService, _Repo]:
    repo = _Repo(credits or [], recurring or [], spent or {})
    return SummaryService(cast(Any, repo), cast(Any, _Currencies())), repo


def _moscow_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)


async def test_31st_falls_on_last_day_of_february() -> None:
    service, _ = _service([_Credit("Альфа", Decimal("10700"), payment_day=31)])
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=30,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2027, 2, 10)),
    )
    # Окно до 12 марта: 31 марта в него не попадает.
    assert [(p.kind, p.name, p.due_date) for p in result] == [
        ("credit", "Альфа", date(2027, 2, 28)),
    ]
    assert result[0].amount == Decimal("10700")
    assert result[0].currency_code == "RUB"
    assert result[0].amount_rub == Decimal("10700")


async def test_leap_february_and_month_after() -> None:
    service, _ = _service([_Credit("Альфа", Decimal("10700"), payment_day=31)])
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=70,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2028, 1, 25)),
    )
    assert [p.due_date for p in result] == [
        date(2028, 1, 31),
        date(2028, 2, 29),
        date(2028, 3, 31),
    ]


async def test_quiet_window_is_empty() -> None:
    """Платёж 4-го уже прошёл, следующий — за окном, план закрыт."""
    rent = _Recurring("Аренда", Decimal("19500"))
    service, _ = _service(
        [_Credit("Альфа", Decimal("10700"), payment_day=4)],
        recurring=[rent],
        spent={rent.category_id: Decimal("-19500")},
    )
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=20,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2026, 8, 10)),
    )
    assert result == []


async def test_payment_due_today_is_shown() -> None:
    """В день платежа о нём надо напомнить, а не промолчать."""
    service, _ = _service([_Credit("Альфа", Decimal("10700"), payment_day=20)])
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=1,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2026, 8, 20)),
    )
    assert [p.due_date for p in result] == [date(2026, 8, 20)]


async def test_today_is_taken_in_the_owner_timezone() -> None:
    """31 августа 22:00 UTC — в Москве уже 1 сентября."""
    rent = _Recurring("Аренда", Decimal("19500"))
    service, repo = _service(
        [_Credit("Альфа", Decimal("10700"), payment_day=1)],
        recurring=[rent],
    )
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=5,
        timezone_name="Europe/Moscow",
        now=datetime(2026, 8, 31, 22, 0, tzinfo=UTC),
    )
    assert result[0].due_date == date(2026, 9, 1)
    # Траты сверяются с сентябрём, а не с августом.
    start, _ = repo.spending_periods[0]
    assert start == datetime(2026, 8, 31, 21, 0, tzinfo=UTC)


async def test_plan_minimum_left_goes_last_without_date() -> None:
    rent = _Recurring("Аренда", Decimal("19500"))
    internet = _Recurring("Интернет", Decimal("650"))
    service, _ = _service(
        [
            _Credit("Сбер", Decimal("5000"), payment_day=25),
            _Credit("Альфа", Decimal("10700"), payment_day=20),
        ],
        recurring=[rent, internet],
        # Аренду заплатили частично, интернет — полностью.
        spent={
            rent.category_id: Decimal("-9500"),
            internet.category_id: Decimal("-650"),
        },
    )
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=30,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2026, 8, 10)),
    )
    assert [(p.kind, p.name, p.due_date) for p in result] == [
        ("credit", "Альфа", date(2026, 8, 20)),
        ("credit", "Сбер", date(2026, 8, 25)),
        ("recurring", "Аренда", None),
    ]
    rent_left = result[-1]
    assert rent_left.amount == Decimal("10000")
    assert rent_left.currency_code == "RUB"
    assert rent_left.amount_rub == Decimal("10000")


async def test_foreign_credit_keeps_its_currency() -> None:
    service, _ = _service(
        [
            _Credit("Uzum", Decimal("1000000"), 15, currency="UZS"),
            _Credit("Евро", Decimal("300"), 16, currency="EUR"),
        ]
    )
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=10,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2026, 8, 10)),
    )
    uzs, eur = result
    assert (uzs.amount, uzs.currency_code) == (Decimal("1000000"), "UZS")
    assert uzs.amount_rub == Decimal("7200.0000")
    # Нет курса — платёж всё равно виден, только без рублей.
    assert (eur.amount, eur.currency_code) == (Decimal("300"), "EUR")
    assert eur.amount_rub is None


async def test_credit_without_schedule_is_skipped() -> None:
    service, _ = _service(
        [
            _Credit("Без дня", Decimal("1000"), payment_day=None),
            _Credit("Без платежа", None, payment_day=15),
        ]
    )
    result = await service.upcoming_payments(
        uuid.uuid4(),
        days=30,
        timezone_name="Europe/Moscow",
        now=_moscow_noon(date(2026, 8, 10)),
    )
    assert result == []
