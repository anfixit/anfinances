"""Проценты и комиссии кредита попадают в расходы.

Проверяется на настоящей сессии, а не на заглушке. Прежняя версия
этих тестов подменяла сессию ``AsyncMock``: SQL в них не
компилировался, поэтому запрос с неразрешимым JOIN проходил проверки
зелёным и падал уже на проде. Заглушка подтверждала только форму
возвращаемого значения — ровно то, что и так очевидно из кода.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.domains.budgets.repository import SqlBudgetRepository
from app.domains.categories.models import Category
from app.domains.credits.expense_projection import (
    credit_expense_total_rub,
    credit_expenses_by_category_rub,
)
from app.domains.credits.models import Credit, CreditPayment
from app.domains.summary.repository import SqlSummaryRepository
from app.domains.transactions.models import Transaction

DATE_FROM = datetime(2026, 1, 1, tzinfo=UTC)
DATE_TO = datetime(2026, 2, 1, tzinfo=UTC)
WHEN = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


async def _payment(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    *,
    interest: Decimal,
    fee: Decimal = Decimal(0),
    rate: Decimal = Decimal(1),
    currency: str = "RUB",
    account_key: str = "rub",
    interest_category: uuid.UUID | None = None,
    fee_category: uuid.UUID | None = None,
    when: datetime = WHEN,
) -> None:
    """Платёж по кредиту вместе со связанной транзакцией."""
    user = ledger["user"]
    account = ledger[account_key]
    principal = Decimal("1000")
    total = principal + interest + fee

    credit = Credit(
        user_id=user,
        name="Кредит",
        currency_code=currency,
        principal_initial=Decimal("100000"),
        principal_balance=Decimal("99000"),
    )
    db_session.add(credit)
    await db_session.flush()

    tx = Transaction(
        user_id=user,
        account_id=account,
        kind=TransactionKind.CREDIT_PAYMENT,
        amount=-total,
        currency_code=currency,
        amount_rub=-total * rate,
        exchange_rate=rate,
        date=when,
    )
    db_session.add(tx)
    await db_session.flush()

    db_session.add(
        CreditPayment(
            user_id=user,
            credit_id=credit.id,
            payment_account_id=account,
            transaction_id=tx.id,
            date=when,
            total_amount=total,
            principal_amount=principal,
            interest_amount=interest,
            fee_amount=fee,
            currency_code=currency,
            interest_category_id=interest_category,
            fee_category_id=fee_category,
        )
    )
    await db_session.flush()


async def test_total_is_negative_and_in_roubles(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _payment(db_session, ledger, interest=Decimal("7979.81"))
    total = await credit_expense_total_rub(
        db_session, ledger["user"], DATE_FROM, DATE_TO
    )
    assert total == Decimal("-7979.81")


async def test_fee_is_counted_together_with_interest(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _payment(
        db_session, ledger, interest=Decimal("500"), fee=Decimal("100")
    )
    total = await credit_expense_total_rub(
        db_session, ledger["user"], DATE_FROM, DATE_TO
    )
    assert total == Decimal("-600")


async def test_foreign_currency_uses_the_baked_rate(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Курс берётся из связанной операции, а не текущий."""
    await _payment(
        db_session,
        ledger,
        interest=Decimal("10000"),
        rate=Decimal("0.0072"),
        currency="UZS",
        account_key="uzs",
    )
    total = await credit_expense_total_rub(
        db_session, ledger["user"], DATE_FROM, DATE_TO
    )
    assert total == Decimal("-72.0000")


async def test_payment_outside_period_is_ignored(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _payment(
        db_session,
        ledger,
        interest=Decimal("500"),
        when=datetime(2026, 3, 1, tzinfo=UTC),
    )
    total = await credit_expense_total_rub(
        db_session, ledger["user"], DATE_FROM, DATE_TO
    )
    assert total == Decimal(0)


async def test_grouped_by_category(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    interest_category = uuid.uuid4()
    await _payment(
        db_session,
        ledger,
        interest=Decimal("300"),
        fee=Decimal("50"),
        interest_category=None,
        fee_category=None,
    )
    spending = await credit_expenses_by_category_rub(
        db_session,
        ledger["user"],
        date_from=DATE_FROM,
        date_to=DATE_TO,
    )
    # Категории не заданы — обе суммы падают в «без категории».
    assert spending == {None: Decimal("-350")}
    assert interest_category not in spending


async def test_cashflow_includes_credit_interest(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Проценты по кредиту — такой же расход, как остальные."""
    db_session.add(
        Transaction(
            user_id=ledger["user"],
            account_id=ledger["rub"],
            kind=TransactionKind.EXPENSE,
            amount=Decimal("-3000"),
            currency_code="RUB",
            amount_rub=Decimal("-3000"),
            exchange_rate=Decimal(1),
            date=WHEN,
        )
    )
    await _payment(db_session, ledger, interest=Decimal("1000"))

    income, expense = await SqlSummaryRepository(db_session).cashflow(
        ledger["user"], DATE_FROM, DATE_TO
    )
    assert income == Decimal(0)
    assert expense == Decimal("-4000")


async def test_summary_repository_merges_credit_spending(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _payment(db_session, ledger, interest=Decimal("700"))
    rows = await SqlSummaryRepository(db_session).spending_by_category(
        ledger["user"], DATE_FROM, DATE_TO
    )
    assert dict(rows) == {None: Decimal("-700")}


async def test_budget_repository_merges_credit_spending(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Проценты попадают в конверт своей категории.

    Траты без категории бюджет намеренно пропускает: конверта для
    них нет, и приписывать их некуда.
    """
    category = Category(
        user_id=ledger["user"], name="Проценты", kind=CategoryKind.EXPENSE
    )
    db_session.add(category)
    await db_session.flush()

    await _payment(
        db_session,
        ledger,
        interest=Decimal("700"),
        interest_category=category.id,
    )
    spent = await SqlBudgetRepository(db_session).spent_by_category(
        ledger["user"], DATE_FROM, DATE_TO
    )
    assert spent == {category.id: Decimal("-700")}
