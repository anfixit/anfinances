"""Проекция графика погашения кредита.

Срок не хранится, а вычисляется из остатка долга, ставки и
обязательного платежа. Тогда досрочное погашение автоматически
укорачивает срок: пользователю не приходится вручную сообщать,
сколько месяцев «съела» переплата.

Проценты начисляются по фактическим дням (actual/365) — так считает
банк, и только так сходится разбивка платежа до копейки. Ровная
двенадцатая часть года даёт ошибку около сотни рублей на платёж.

Даты платежей строятся по дню платежа из договора. Банк переносит
попавшие на выходные даты на ближайший рабочий день; здесь этого
переноса нет, поэтому проценты могут отличаться на день начисления.
Для ближайшего платежа расхождения обычно нет, для дальних —
накапливается порядка процента.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

__all__ = [
    "CreditProjection",
    "NeverAmortizesError",
    "ScheduledPayment",
    "project_credit",
]

_CENTS = Decimal("0.01")
_DAYS_IN_YEAR = Decimal(365)
_MAX_PAYMENTS = 600  # 50 лет — дальше считать бессмысленно


class NeverAmortizesError(ValueError):
    """Платёж не покрывает проценты — долг никогда не погасится."""


@dataclass(frozen=True)
class ScheduledPayment:
    date: date
    total: Decimal
    principal: Decimal
    interest: Decimal


@dataclass(frozen=True)
class CreditProjection:
    remaining_payments: int
    last_payment_date: date | None
    last_payment_amount: Decimal | None
    total_interest_remaining: Decimal
    next_payment: ScheduledPayment | None


def project_credit(
    *,
    balance: Decimal,
    annual_rate: Decimal,
    monthly_payment: Decimal,
    payment_day: int,
    since: date,
) -> CreditProjection:
    """Построить проекцию оставшихся платежей.

    ``annual_rate`` — годовая ставка в процентах (21.59, не 0.2159).
    ``since`` — дата, от которой считаются проценты: обычно дата
    последнего внесённого платежа или дата выдачи кредита.
    """
    if balance <= 0:
        return CreditProjection(
            remaining_payments=0,
            last_payment_date=None,
            last_payment_amount=None,
            total_interest_remaining=Decimal(0),
            next_payment=None,
        )

    rate = annual_rate / Decimal(100)
    remaining = balance
    previous = since
    interest_total = Decimal(0)
    first: ScheduledPayment | None = None
    last_date = since
    last_amount = Decimal(0)
    count = 0

    while remaining > 0:
        if count >= _MAX_PAYMENTS:
            raise NeverAmortizesError(
                "Платёж не гасит долг за разумный срок: проверьте "
                "сумму платежа и ставку."
            )

        due = _next_due(previous, payment_day)
        days = Decimal((due - previous).days)
        interest = (remaining * rate * days / _DAYS_IN_YEAR).quantize(
            _CENTS, ROUND_HALF_UP
        )

        if remaining + interest <= monthly_payment:
            # Последний платёж: остаток долга плюс проценты за период.
            total = (remaining + interest).quantize(_CENTS, ROUND_HALF_UP)
            payment = ScheduledPayment(
                date=due,
                total=total,
                principal=remaining.quantize(_CENTS, ROUND_HALF_UP),
                interest=interest,
            )
            interest_total += interest
            remaining = Decimal(0)
        else:
            principal = monthly_payment - interest
            if principal <= 0:
                raise NeverAmortizesError(
                    "Платёж меньше начисленных процентов: долг растёт, "
                    "а не гасится."
                )
            payment = ScheduledPayment(
                date=due,
                total=monthly_payment,
                principal=principal.quantize(_CENTS, ROUND_HALF_UP),
                interest=interest,
            )
            interest_total += interest
            remaining -= principal

        if first is None:
            first = payment
        last_date = payment.date
        last_amount = payment.total
        previous = due
        count += 1

    return CreditProjection(
        remaining_payments=count,
        last_payment_date=last_date,
        last_payment_amount=last_amount,
        total_interest_remaining=interest_total.quantize(
            _CENTS, ROUND_HALF_UP
        ),
        next_payment=first,
    )


def _next_due(after: date, payment_day: int) -> date:
    """Следующая дата платежа строго после ``after``.

    День платежа обрезается до длины месяца: 31-е в феврале — это
    28-е или 29-е.
    """
    year, month = after.year, after.month
    day = min(payment_day, monthrange(year, month)[1])
    candidate = date(year, month, day)
    if candidate > after:
        return candidate

    month += 1
    if month > 12:
        month = 1
        year += 1
    day = min(payment_day, monthrange(year, month)[1])
    return date(year, month, day)
