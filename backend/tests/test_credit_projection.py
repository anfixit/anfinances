"""Проекция графика погашения кредита.

Эталон — реальный график Альфа-Банка по кредиту владельца:
остаток 280 650,24 ₽, ставка 21,59%, платёж 10 700 ₽, день платежа 4.
Банк начисляет проценты по фактическим дням (actual/365), а не ровной
двенадцатой частью года — это видно по разнице между платежами
с интервалом 30 и 31 день.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.credits.projection import (
    NeverAmortizesError,
    project_credit,
)

BALANCE = Decimal("280650.24")
RATE = Decimal("21.59")
PAYMENT = Decimal("10700")
SINCE = date(2026, 8, 4)


def _project(**overrides: object) -> object:
    kwargs: dict[str, object] = {
        "balance": BALANCE,
        "annual_rate": RATE,
        "monthly_payment": PAYMENT,
        "payment_day": 4,
        "since": SINCE,
    }
    kwargs.update(overrides)
    return project_credit(**kwargs)  # type: ignore[arg-type]


def test_remaining_payments_match_bank() -> None:
    """Банк показывает 43 платежа всего, внесено 7 — осталось 36."""
    assert _project().remaining_payments == 36  # type: ignore[attr-defined]


def test_next_payment_split_matches_bank_to_the_kopeck() -> None:
    """4 сентября: тело 5 553,80, проценты 5 146,20."""
    nxt = _project().next_payment  # type: ignore[attr-defined]
    assert nxt.date == date(2026, 9, 4)
    assert nxt.interest == Decimal("5146.20")
    assert nxt.principal == Decimal("5553.80")
    assert nxt.total == PAYMENT


def test_last_payment_is_smaller_and_dated_by_bank() -> None:
    projection = _project()
    assert projection.last_payment_date == date(2029, 8, 4)  # type: ignore[attr-defined]
    assert projection.last_payment_amount < PAYMENT  # type: ignore[attr-defined]


def test_extra_payment_shortens_the_term() -> None:
    """Пятьдесят тысяч сверху — минус восемь месяцев."""
    assert _project(balance=Decimal("230650.24")).remaining_payments == 28  # type: ignore[attr-defined]
    assert _project(balance=Decimal("180650.24")).remaining_payments == 21  # type: ignore[attr-defined]


def test_total_interest_remaining_is_positive_and_sane() -> None:
    projection = _project()
    # За 36 платежей по 10 700 будет уплачено ~385 200, из них тело
    # 280 650 — значит процентов около сотни тысяч.
    assert Decimal("80000") < projection.total_interest_remaining  # type: ignore[attr-defined]
    assert projection.total_interest_remaining < Decimal("120000")  # type: ignore[attr-defined]


def test_zero_balance_gives_empty_projection() -> None:
    projection = _project(balance=Decimal("0"))
    assert projection.remaining_payments == 0  # type: ignore[attr-defined]
    assert projection.next_payment is None  # type: ignore[attr-defined]


def test_payment_smaller_than_interest_never_amortizes() -> None:
    """Платёж меньше процентов — долг растёт, срок бесконечен."""
    with pytest.raises(NeverAmortizesError):
        _project(monthly_payment=Decimal("100"))


def test_zero_rate_is_simple_division() -> None:
    projection = _project(
        balance=Decimal("30000"),
        annual_rate=Decimal("0"),
        monthly_payment=Decimal("10000"),
    )
    assert projection.remaining_payments == 3  # type: ignore[attr-defined]


def test_payment_day_beyond_month_length_clamps() -> None:
    """31-е число в феврале — берём последний день месяца."""
    projection = _project(
        payment_day=31,
        since=date(2027, 1, 31),
        balance=Decimal("20000"),
    )
    assert projection.next_payment.date == date(2027, 2, 28)  # type: ignore[attr-defined]
