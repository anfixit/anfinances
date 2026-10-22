"""План погашения на уровне сервиса: данные из базы, валюты, отказы.

Чистая математика проверена в test_credit_payoff. Здесь — то, что
сервис добавляет: откуда берётся дата отсчёта процентов, как
валютный кредит сводится в рубли и что происходит с кредитами,
которые посчитать нельзя. Они не роняют план и не зацикливают его,
а перечисляются с причиной.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.domains.credits.models import Credit, CreditPayment
from app.domains.credits.payoff import PayoffStrategy
from app.domains.credits.repository import SqlCreditRepository
from app.domains.credits.service import CreditService

USER = uuid.uuid4()
# 22 октября 2026, полдень по Москве.
NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)


def _credit(
    name: str,
    balance: str,
    *,
    rate: str | None = "20",
    payment: str | None = "10000",
    day: int | None = 15,
    start: date | None = date(2026, 1, 15),
    currency: str = "RUB",
) -> Credit:
    return Credit(
        id=uuid.uuid4(),
        user_id=USER,
        name=name,
        currency_code=currency,
        principal_initial=Decimal(balance),
        principal_balance=Decimal(balance),
        annual_rate=None if rate is None else Decimal(rate),
        monthly_payment=None if payment is None else Decimal(payment),
        payment_day=day,
        start_date=start,
        is_archived=False,
    )


class _Repo:
    def __init__(
        self,
        credits: list[Credit],
        paid: dict[uuid.UUID, datetime] | None = None,
    ) -> None:
        self._credits = credits
        self._paid = paid or {}

    async def list_active(self, user_id: uuid.UUID) -> list[Credit]:
        return [c for c in self._credits if not c.is_archived]

    async def last_payment_dates(
        self, user_id: uuid.UUID
    ) -> dict[uuid.UUID, datetime]:
        return dict(self._paid)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        rates = {"RUB": Decimal(1), "USD": Decimal("90")}
        if code not in rates:
            raise NotFoundError(f"Нет курса для валюты {code}.")
        return rates[code]


def _service(repo: _Repo) -> CreditService:
    return CreditService(
        cast(Any, repo),
        cast(Any, None),
        currencies=cast(Any, _Currencies()),
    )


async def test_plan_reports_what_it_could_not_count() -> None:
    good = _credit("Альфа", "100000")
    no_rate = _credit("Без ставки", "50000", rate=None)
    no_start = _credit("Без даты", "50000", start=None)
    euro = _credit("Евро", "1000", currency="EUR", payment="100")
    hopeless = _credit("Микрозайм", "100000", rate="36", payment="100")
    paid_off = _credit("Закрыт", "0")
    service = _service(
        _Repo([good, no_rate, no_start, euro, hopeless, paid_off])
    )

    plan = await service.payoff_plan(
        USER, PayoffStrategy.AVALANCHE, Decimal(0), "Europe/Moscow", NOW
    )

    assert [item.name for item in plan.order] == ["Альфа"]
    assert {(s.name, s.reason) for s in plan.skipped} == {
        ("Без ставки", "missing_terms"),
        ("Без даты", "missing_terms"),
        ("Евро", "missing_rate"),
        ("Микрозайм", "never_amortizes"),
    }
    assert all(s.message for s in plan.skipped)
    assert plan.months_to_debt_free > 0


async def test_interest_counts_from_the_last_payment() -> None:
    """Платёж 15 октября внесён — следующий 15 ноября, не сегодня."""
    credit = _credit("Альфа", "9000", rate="0", payment="3000")
    service = _service(
        _Repo([credit], {credit.id: datetime(2026, 10, 15, 7, tzinfo=UTC)})
    )
    plan = await service.payoff_plan(
        USER, PayoffStrategy.SNOWBALL, Decimal(0), "Europe/Moscow", NOW
    )
    assert plan.order[0].payoff_date == date(2027, 1, 15)
    assert plan.debt_free_date == date(2027, 1, 15)
    assert plan.months_to_debt_free == 3


async def test_foreign_credit_is_planned_in_rubles() -> None:
    """Доплата в рублях делится между кредитами в разных валютах."""
    rub = _credit("Рубли", "100000", rate="0", payment="10000")
    usd = _credit("Доллары", "1000", rate="0", payment="100", currency="USD")
    service = _service(_Repo([rub, usd]))

    plan = await service.payoff_plan(
        USER, PayoffStrategy.SNOWBALL, Decimal("9000"), "Europe/Moscow", NOW
    )

    # 1 000 $ = 90 000 ₽ меньше 100 000 ₽ — снежный ком начинает с него.
    assert [(i.name, i.currency_code) for i in plan.order] == [
        ("Доллары", "USD"),
        ("Рубли", "RUB"),
    ]
    # 9 000 + 9 000 обязательного в месяц: 90 000 ₽ — за пять месяцев.
    assert plan.order[0].payoff_date == date(2027, 3, 15)


async def test_savings_are_measured_against_the_baseline() -> None:
    credits = [
        _credit("Кредитка", "120000", rate="34.9", payment="6000", day=25),
        _credit("Сбер", "50000", rate="12", payment="3000", day=15),
    ]
    service = _service(_Repo(credits))

    plan = await service.payoff_plan(
        USER, PayoffStrategy.AVALANCHE, Decimal("5000"), "Europe/Moscow", NOW
    )

    assert plan.strategy == PayoffStrategy.AVALANCHE
    assert plan.extra_monthly == Decimal("5000")
    assert plan.interest_saved == (
        plan.baseline.total_interest - plan.total_interest
    )
    assert plan.interest_saved > 0
    assert plan.months_saved == (
        plan.baseline.months_to_debt_free - plan.months_to_debt_free
    )
    assert plan.months_saved > 0
    assert plan.total_interest == sum(i.interest_paid for i in plan.order)


async def test_no_credits_gives_an_empty_plan() -> None:
    plan = await _service(_Repo([])).payoff_plan(
        USER, PayoffStrategy.AVALANCHE, Decimal(0), "Europe/Moscow", NOW
    )
    assert plan.order == []
    assert plan.debt_free_date is None
    assert plan.months_to_debt_free == 0
    assert plan.baseline.months_to_debt_free == 0
    assert plan.interest_saved == Decimal(0)


async def test_last_payment_dates_query_runs(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Запрос выполняется на настоящей сессии, а не только строится."""
    credit = Credit(
        user_id=ledger["user"],
        name="Альфа",
        currency_code="RUB",
        principal_initial=Decimal("100000"),
        principal_balance=Decimal("90000"),
    )
    db_session.add(credit)
    await db_session.flush()
    for day in (4, 20, 9):
        db_session.add(
            CreditPayment(
                user_id=ledger["user"],
                credit_id=credit.id,
                payment_account_id=ledger["rub"],
                date=datetime(2026, 9, day, 7, 0, tzinfo=UTC),
                total_amount=Decimal("1000"),
                principal_amount=Decimal("1000"),
                interest_amount=Decimal(0),
                fee_amount=Decimal(0),
                currency_code="RUB",
            )
        )
    await db_session.flush()

    dates = await SqlCreditRepository(db_session).last_payment_dates(
        ledger["user"]
    )

    assert list(dates) == [credit.id]
    assert dates[credit.id].date() == date(2026, 9, 20)
