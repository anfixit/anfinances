"""План погашения всех кредитов: лавина против снежного кома.

Цель владельца — закрыть все кредиты. Ассистент сравнивает
стратегии и доплаты, поэтому важно три вещи: очередь целей,
переток высвободившегося платежа на следующую цель и честная база
для сравнения — тот же график, что на странице кредита.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domains.credits.payoff import (
    PayoffDebt,
    PayoffStrategy,
    baseline_payoff,
    effective_since,
    months_until,
    prioritize,
    simulate_payoff,
)
from app.domains.credits.projection import (
    NeverAmortizesError,
    project_credit,
)

TODAY = date(2026, 10, 22)


def _debt(
    name: str,
    balance: str,
    rate: str,
    payment: str,
    day: int,
    since: date,
) -> PayoffDebt:
    return PayoffDebt(
        key=uuid.uuid4(),
        name=name,
        balance=Decimal(balance),
        annual_rate=Decimal(rate),
        monthly_payment=Decimal(payment),
        payment_day=day,
        since=since,
    )


# Три кредита: дорогая кредитка, большой потребительский и
# маленький дешёвый — у лавины и снежного кома разные первые цели.
ALFA = _debt("Альфа", "280650.24", "21.59", "10700", 4, date(2026, 10, 4))
SBER = _debt("Сбер", "50000", "12", "3000", 15, date(2026, 10, 15))
CARD = _debt("Кредитка", "120000", "34.9", "6000", 25, date(2026, 9, 25))
THREE = [ALFA, SBER, CARD]


def test_avalanche_attacks_the_highest_rate_first() -> None:
    order = prioritize(THREE, PayoffStrategy.AVALANCHE)
    assert [d.name for d in order] == ["Кредитка", "Альфа", "Сбер"]


def test_snowball_attacks_the_smallest_balance_first() -> None:
    order = prioritize(THREE, PayoffStrategy.SNOWBALL)
    assert [d.name for d in order] == ["Сбер", "Кредитка", "Альфа"]


def test_plan_lists_credits_in_strategy_order() -> None:
    plan = simulate_payoff(
        THREE, PayoffStrategy.SNOWBALL, Decimal("10000"), TODAY
    )
    assert [d.name for d in plan.debts] == ["Сбер", "Кредитка", "Альфа"]
    # Снежный ком закрывает первую цель раньше всех остальных.
    payoff = {d.name: d.payoff_date for d in plan.debts}
    assert payoff["Сбер"] < payoff["Кредитка"] < payoff["Альфа"]


def test_avalanche_pays_less_interest_than_snowball() -> None:
    avalanche = simulate_payoff(
        THREE, PayoffStrategy.AVALANCHE, Decimal("10000"), TODAY
    )
    snowball = simulate_payoff(
        THREE, PayoffStrategy.SNOWBALL, Decimal("10000"), TODAY
    )
    assert avalanche.total_interest < snowball.total_interest
    assert avalanche.debt_free_date is not None
    assert snowball.debt_free_date is not None


def test_both_strategies_beat_the_baseline() -> None:
    baseline = baseline_payoff(THREE, TODAY)
    for strategy in PayoffStrategy:
        plan = simulate_payoff(THREE, strategy, Decimal("10000"), TODAY)
        assert plan.total_interest < baseline.total_interest
        assert plan.months_to_debt_free < baseline.months_to_debt_free


def test_freed_payment_rolls_over_to_the_next_target() -> None:
    """Беспроцентные рассрочки: считается в уме.

    Маленькая закрывается за три платежа, дальше её тысяча идёт в
    большую: 12 000 − 3 × 1 000 = 9 000 по 2 000 в месяц — ещё пять
    платежей. Без перетока большая шла бы все двенадцать.
    """
    small = _debt("Телефон", "3000", "0", "1000", 10, date(2026, 10, 10))
    big = _debt("Диван", "12000", "0", "1000", 10, date(2026, 10, 10))

    plan = simulate_payoff(
        [big, small], PayoffStrategy.SNOWBALL, Decimal(0), TODAY
    )
    payoff = {d.name: d.payoff_date for d in plan.debts}
    assert payoff["Телефон"] == date(2027, 1, 10)
    assert payoff["Диван"] == date(2027, 6, 10)

    baseline = baseline_payoff([big, small], TODAY)
    assert baseline.debt_free_date == date(2027, 10, 10)
    assert baseline.total_interest == plan.total_interest == Decimal("0.00")


def test_leftover_of_a_closing_credit_goes_to_the_target_same_month() -> None:
    """Последний платёж меньше обязательного — разница не пропадает."""
    small = _debt("Телефон", "2500", "0", "1000", 10, date(2026, 10, 10))
    big = _debt("Диван", "12000", "0", "1000", 10, date(2026, 10, 10))

    plan = simulate_payoff(
        [big, small], PayoffStrategy.SNOWBALL, Decimal(0), TODAY
    )
    # Три месяца: 1 000 + 1 000 + 1 500 → осталось 8 500, дальше по
    # 2 000 — ещё пять платежей, последний 500.
    payoff = {d.name: d.payoff_date for d in plan.debts}
    assert payoff["Телефон"] == date(2027, 1, 10)
    assert payoff["Диван"] == date(2027, 6, 10)


def test_extra_goes_to_the_next_target_once_the_first_is_closed() -> None:
    small = _debt("Телефон", "1500", "0", "1000", 10, date(2026, 10, 10))
    big = _debt("Диван", "12000", "0", "1000", 10, date(2026, 10, 10))

    plan = simulate_payoff(
        [big, small], PayoffStrategy.SNOWBALL, Decimal("1000"), TODAY
    )
    # Первый месяц: 1 000 + 500 доплаты закрывают телефон, ещё 500
    # доплаты сразу уходят в диван: 12 000 − 1 000 − 500 = 10 500.
    # Дальше по 3 000 — ещё четыре платежа.
    payoff = {d.name: d.payoff_date for d in plan.debts}
    assert payoff["Телефон"] == date(2026, 11, 10)
    assert payoff["Диван"] == date(2027, 3, 10)


def test_single_credit_without_extra_matches_its_own_schedule() -> None:
    """Та же формула процентов: план совпадает с графиком банка."""
    plan = simulate_payoff([ALFA], PayoffStrategy.AVALANCHE, Decimal(0), TODAY)
    projection = project_credit(
        balance=ALFA.balance,
        annual_rate=ALFA.annual_rate,
        monthly_payment=ALFA.monthly_payment,
        payment_day=ALFA.payment_day,
        since=ALFA.since,
    )
    baseline = baseline_payoff([ALFA], TODAY)

    assert plan.total_interest == projection.total_interest_remaining
    assert plan.debt_free_date == projection.last_payment_date
    assert baseline.total_interest == plan.total_interest
    assert baseline.months_to_debt_free == plan.months_to_debt_free


def test_extra_payment_shortens_the_term_and_saves_interest() -> None:
    baseline = baseline_payoff([ALFA], TODAY)
    plan = simulate_payoff(
        [ALFA], PayoffStrategy.AVALANCHE, Decimal("5000"), TODAY
    )
    assert plan.months_to_debt_free < baseline.months_to_debt_free
    assert plan.total_interest < baseline.total_interest


def test_credit_that_never_amortizes_is_reported_not_looped() -> None:
    hopeless = _debt("Микрозайм", "100000", "36", "100", 5, TODAY)
    with pytest.raises(NeverAmortizesError):
        baseline_payoff([hopeless], TODAY)
    with pytest.raises(NeverAmortizesError):
        simulate_payoff([hopeless], PayoffStrategy.SNOWBALL, Decimal(0), TODAY)


def test_no_credits_means_debt_free_now() -> None:
    plan = simulate_payoff(
        [], PayoffStrategy.AVALANCHE, Decimal("5000"), TODAY
    )
    assert plan.months_to_debt_free == 0
    assert plan.debt_free_date is None
    assert plan.total_interest == Decimal(0)


def test_stale_since_starts_from_the_last_past_due_date() -> None:
    """Платежи давно не вносились — план всё равно начинается с
    ближайшего будущего платежа, а не с полугода назад."""
    assert effective_since(date(2026, 3, 4), 4, TODAY) == date(2026, 10, 4)
    # Свежий платёж не трогаем.
    assert effective_since(date(2026, 10, 4), 4, TODAY) == date(2026, 10, 4)
    # Платёж сегодня ещё впереди: отсчёт — от прошлого месяца.
    assert effective_since(date(2026, 9, 22), 22, TODAY) == date(2026, 9, 22)


def test_months_until_counts_partial_month_as_whole() -> None:
    assert months_until(TODAY, date(2026, 11, 4)) == 1
    assert months_until(TODAY, date(2026, 10, 25)) == 1
    assert months_until(TODAY, date(2026, 11, 25)) == 2
    assert months_until(TODAY, TODAY) == 0
