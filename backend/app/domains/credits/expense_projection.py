"""Расходная проекция процентов и комиссий по кредитам."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.credits.models import CreditPayment
from app.domains.transactions.models import Transaction

__all__ = [
    "credit_expense_total_rub",
    "credit_expenses_by_category_rub",
]


async def credit_expense_total_rub(
    session: AsyncSession,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
) -> Decimal:
    """Вернуть проценты и комиссии за период в рублях со знаком минус."""
    result = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    -(CreditPayment.interest_amount + CreditPayment.fee_amount)
                    * Transaction.exchange_rate
                ),
                Decimal(0),
            )
        )
        .join(
            Transaction,
            Transaction.id == CreditPayment.transaction_id,
        )
        .where(
            CreditPayment.user_id == user_id,
            Transaction.user_id == user_id,
            CreditPayment.date >= date_from,
            CreditPayment.date < date_to,
        )
    )
    return result.scalar_one()


async def credit_expenses_by_category_rub(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[uuid.UUID | None, Decimal]:
    """Сгруппировать проценты и комиссии по расходным категориям."""
    conditions = [
        CreditPayment.user_id == user_id,
        Transaction.user_id == user_id,
    ]
    if date_from is not None:
        conditions.append(CreditPayment.date >= date_from)
    if date_to is not None:
        conditions.append(CreditPayment.date < date_to)

    interest = (
        select(
            CreditPayment.interest_category_id.label("category_id"),
            (-CreditPayment.interest_amount * Transaction.exchange_rate).label(
                "amount_rub"
            ),
        )
        .join(
            Transaction,
            Transaction.id == CreditPayment.transaction_id,
        )
        .where(
            *conditions,
            CreditPayment.interest_amount > 0,
        )
    )
    fee = (
        select(
            CreditPayment.fee_category_id.label("category_id"),
            (-CreditPayment.fee_amount * Transaction.exchange_rate).label(
                "amount_rub"
            ),
        )
        .join(
            Transaction,
            Transaction.id == CreditPayment.transaction_id,
        )
        .where(
            *conditions,
            CreditPayment.fee_amount > 0,
        )
    )
    components = union_all(interest, fee).subquery()
    result = await session.execute(
        select(
            components.c.category_id,
            func.coalesce(
                func.sum(components.c.amount_rub),
                Decimal(0),
            ),
        ).group_by(components.c.category_id)
    )
    return {row[0]: row[1] for row in result.all()}
