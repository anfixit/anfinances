"""План погашения всех кредитов сразу: лавина и снежный ком.

Каждый месяц на кредиты уходит одна и та же сумма: обязательные
платежи всех начатых кредитов плюс ``extra`` сверху. Сначала по
каждому кредиту вносится его обязательный платёж, остаток бюджета
целиком идёт в досрочное погашение кредита-цели. Когда кредит
закрыт, его платёж не исчезает из бюджета, а переходит на
следующую цель — в этом и смысл обеих стратегий.

Лавина (avalanche) первой гасит самую дорогую ставку — меньше
переплата. Снежный ком (snowball) — самый маленький остаток: первый
закрытый кредит виден быстрее, и это держит мотивацию.

Проценты и даты — та же формула, что в графике одного кредита
(``projection``): фактические дни, actual/365, до копейки. Поэтому
план с нулевой доплатой по одному кредиту совпадает с его графиком.

Месяц здесь — календарный. Досрочка вносится в день платежа цели;
если в том же месяце кредит закрылся позже этой даты, его
высвободившийся остаток всё равно учитывается в этом месяце. На
горизонте в годы это расхождение в днях не меняет вывода.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domains.credits.projection import (
    MAX_PAYMENTS,
    NeverAmortizesError,
    accrued_interest,
    next_due,
    project_credit,
)

__all__ = [
    "DebtOutcome",
    "PayoffDebt",
    "PayoffOutcome",
    "PayoffStrategy",
    "baseline_payoff",
    "effective_since",
    "months_until",
    "prioritize",
    "simulate_payoff",
]

_CENTS = Decimal("0.01")


class PayoffStrategy(StrEnum):
    AVALANCHE = "avalanche"
    SNOWBALL = "snowball"


@dataclass(frozen=True)
class PayoffDebt:
    """Кредит для плана: суммы уже в одной валюте (рублях)."""

    key: uuid.UUID
    name: str
    balance: Decimal
    annual_rate: Decimal  # в процентах: 21.59, не 0.2159
    monthly_payment: Decimal
    payment_day: int
    since: date  # от этой даты начисляются проценты


@dataclass(frozen=True)
class DebtOutcome:
    key: uuid.UUID
    name: str
    payoff_date: date
    interest_paid: Decimal


@dataclass(frozen=True)
class PayoffOutcome:
    months_to_debt_free: int
    debt_free_date: date | None
    total_interest: Decimal
    debts: list[DebtOutcome]


@dataclass
class _State:
    debt: PayoffDebt
    remaining: Decimal
    previous: date
    due: date
    first_month: int
    interest: Decimal = field(default_factory=Decimal)
    payoff: date | None = None


def effective_since(since: date, payment_day: int, today: date) -> date:
    """Последняя дата платежа до сегодня, если данные отстали.

    Если платежи давно не вносились, остаток долга считаем
    актуальным на последнюю прошедшую дату платежа, а проценты за
    пропущенные месяцы не досчитываем. Иначе план начинался бы с
    платежей в прошлом, а первый «будущий» платёж нёс бы проценты
    за полгода.
    """
    current = since
    while (due := next_due(current, payment_day)) < today:
        current = due
    return current


def months_until(today: date, end: date) -> int:
    """Сколько месяцев до ``end``, неполный месяц — за целый.

    С 22 октября до 4 ноября — один месяц, до 25 ноября — два.
    """
    months = (end.year - today.year) * 12 + end.month - today.month
    if end.day > today.day:
        months += 1
    return max(months, 0)


def prioritize(
    debts: list[PayoffDebt], strategy: PayoffStrategy
) -> list[PayoffDebt]:
    """Очередь целей для досрочного погашения.

    Равенство разбивается второй характеристикой, а затем именем —
    чтобы план не менялся от порядка строк в базе.
    """
    if strategy is PayoffStrategy.AVALANCHE:
        return sorted(debts, key=lambda d: (-d.annual_rate, d.balance, d.name))
    return sorted(debts, key=lambda d: (d.balance, -d.annual_rate, d.name))


def baseline_payoff(debts: list[PayoffDebt], today: date) -> PayoffOutcome:
    """Каждый кредит по своему графику, без доплат и перетока.

    Это и есть ``project_credit`` по каждому кредиту — та же цифра,
    что на странице кредита. Кредит, чей платёж не покрывает
    проценты, поднимает ``NeverAmortizesError``.
    """
    outcomes: list[DebtOutcome] = []
    for debt in debts:
        if debt.balance <= 0:
            continue
        projection = project_credit(
            balance=debt.balance,
            annual_rate=debt.annual_rate,
            monthly_payment=debt.monthly_payment,
            payment_day=debt.payment_day,
            since=debt.since,
        )
        if projection.last_payment_date is None:
            continue
        outcomes.append(
            DebtOutcome(
                key=debt.key,
                name=debt.name,
                payoff_date=projection.last_payment_date,
                interest_paid=projection.total_interest_remaining,
            )
        )
    return _summarize(outcomes, today)


def simulate_payoff(
    debts: list[PayoffDebt],
    strategy: PayoffStrategy,
    extra_monthly: Decimal,
    today: date,
) -> PayoffOutcome:
    """Погасить все кредиты по стратегии с доплатой ``extra_monthly``.

    ``debts`` в результате — в порядке очереди стратегии: кого гасить
    досрочно первым. Если за ``MAX_PAYMENTS`` месяцев долг не закрыт
    (платёж не покрывает проценты), поднимается
    ``NeverAmortizesError`` — без вечного цикла.
    """
    states = [
        _start(debt)
        for debt in prioritize(debts, strategy)
        if debt.balance > 0
    ]
    if not states:
        return _summarize([], today)

    month = min(state.first_month for state in states)
    for _ in range(MAX_PAYMENTS):
        if all(state.payoff is not None for state in states):
            break
        _pay_month(states, month, extra_monthly)
        month += 1
    else:
        raise NeverAmortizesError(
            "План не гасит долг за разумный срок: платёж по одному из "
            "кредитов не покрывает проценты."
        )

    outcomes = [
        DebtOutcome(
            key=state.debt.key,
            name=state.debt.name,
            payoff_date=state.payoff,
            interest_paid=state.interest.quantize(_CENTS),
        )
        for state in states
        if state.payoff is not None
    ]
    return _summarize(outcomes, today)


def _start(debt: PayoffDebt) -> _State:
    due = next_due(debt.since, debt.payment_day)
    return _State(
        debt=debt,
        remaining=debt.balance,
        previous=debt.since,
        due=due,
        first_month=_month_index(due),
    )


def _pay_month(states: list[_State], month: int, extra: Decimal) -> None:
    """Один календарный месяц: обязательные платежи, затем доплата.

    Бюджет месяца включает платежи уже закрытых кредитов — это и
    есть переток. Кредит, чей первый платёж ещё впереди, в бюджет
    не входит: этих денег владелец пока не платит.
    """
    budget = extra + sum(
        (s.debt.monthly_payment for s in states if s.first_month <= month),
        Decimal(0),
    )
    paying = [
        s for s in states if s.payoff is None and _month_index(s.due) == month
    ]

    for state in paying:
        interest = accrued_interest(
            state.remaining, state.debt.annual_rate, state.previous, state.due
        )
        owed = state.remaining + interest
        payment = min(state.debt.monthly_payment, owed)
        state.remaining = owed - payment
        state.interest += interest
        budget -= payment

    # Список уже в порядке стратегии: остаток бюджета идёт первой
    # цели, а если его хватило её закрыть — следующей.
    for state in paying:
        if budget <= 0:
            break
        extra_payment = min(budget, state.remaining)
        state.remaining -= extra_payment
        budget -= extra_payment

    for state in paying:
        if state.remaining <= 0:
            state.remaining = Decimal(0)
            state.payoff = state.due
        else:
            state.previous = state.due
            state.due = next_due(state.due, state.debt.payment_day)


def _summarize(outcomes: list[DebtOutcome], today: date) -> PayoffOutcome:
    debt_free = max((o.payoff_date for o in outcomes), default=None)
    return PayoffOutcome(
        months_to_debt_free=(
            0 if debt_free is None else months_until(today, debt_free)
        ),
        debt_free_date=debt_free,
        total_interest=sum(
            (o.interest_paid for o in outcomes), Decimal(0)
        ).quantize(_CENTS),
        debts=outcomes,
    )


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1
