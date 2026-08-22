"""Возраст денег: сколько рубль пролежал до траты.

Считается по FIFO, как в YNAB. Тесты проверяют не «работает ли
функция», а что она отвечает на вопрос правильно: свежие деньги
дают маленький возраст, отложенные — большой, а на пустой базе
ответа нет вовсе.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domains.summary.money_age import Flow, age_of_money

START = datetime(2026, 1, 1, tzinfo=UTC)


def _in(day: int, amount: str) -> Flow:
    return Flow(at=START + timedelta(days=day), amount=Decimal(amount))


def _out(day: int, amount: str) -> Flow:
    return Flow(at=START + timedelta(days=day), amount=-Decimal(amount))


def test_spending_the_day_it_arrives_is_zero_days() -> None:
    assert age_of_money([_in(0, "1000"), _out(0, "1000")]) == 0


def test_money_held_a_month_shows_that_month() -> None:
    assert age_of_money([_in(0, "1000"), _out(30, "1000")]) == 30


def test_oldest_money_is_spent_first() -> None:
    """FIFO: сначала тратится то, что пришло раньше."""
    flows = [_in(0, "1000"), _in(20, "1000"), _out(30, "1000")]
    assert age_of_money(flows) == 30


def test_a_single_expense_can_span_two_incomes() -> None:
    """Половина с денег тридцатидневной давности, половина — свежих."""
    flows = [_in(0, "500"), _in(20, "500"), _out(30, "1000")]
    assert age_of_money(flows) == 20


def test_bigger_purchase_weighs_more() -> None:
    """Крупная трата со старых денег важнее мелкой со свежих."""
    flows = [
        _in(0, "10000"),
        _in(40, "10000"),
        _out(50, "9000"),
        _out(50, "1000"),
    ]
    # 9000 пролежали 50 дней, 1000 — тоже из первого прихода.
    assert age_of_money(flows) == 50


def test_nothing_spent_has_no_age() -> None:
    """У новой базы возраст не «ноль дней», его просто ещё нет."""
    assert age_of_money([_in(0, "1000")]) is None


def test_spending_without_income_has_no_age() -> None:
    """Не из чего платить — нечего и старить."""
    assert age_of_money([_out(0, "1000")]) is None


def test_only_recent_expenses_count() -> None:
    """Показатель годичной давности не про сегодняшние привычки."""
    old = [_in(0, "100"), _out(300, "100")]
    fresh = [
        flow
        for day in range(310, 330)
        for flow in (_in(day, "100"), _out(day, "100"))
    ]
    assert age_of_money(old + fresh, window=10) == 0


def test_unsorted_input_is_ordered_first() -> None:
    """Операции приходят как попало; порядок задаёт не запрос, а время."""
    flows = [_out(30, "1000"), _in(0, "1000")]
    assert age_of_money(flows) == 30
