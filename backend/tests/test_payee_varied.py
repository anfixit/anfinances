"""Получатель с разными категориями — память ему не положена.

Ozon продаёт и корм, и поводок для SUP-борда: запомненная категория
подставлялась бы в каждую следующую покупку и каждый раз неверно.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.schemas import PayeeUpdate
from app.domains.payees.service import PayeeService, is_marketplace
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.schemas import TransactionCreate
from app.domains.transactions.service import TransactionService

WHEN = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return Decimal(1)


def _payees(db_session: AsyncSession) -> PayeeService:
    return PayeeService(SqlPayeeRepository(db_session))


async def _spend_at(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    payee: str,
) -> uuid.UUID:
    category = Category(
        user_id=ledger["user"], name="Корм", kind=CategoryKind.EXPENSE
    )
    db_session.add(category)
    await db_session.flush()
    await TransactionService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        cast(Any, _Currencies()),
        _payees(db_session),
    ).create_transaction(
        ledger["user"],
        TransactionCreate(
            account_id=ledger["rub"],
            kind=TransactionKind.EXPENSE,
            amount=Decimal("500"),
            date=WHEN,
            category_id=category.id,
            payee=payee,
        ),
    )
    return category.id


def test_marketplaces_are_recognised_whatever_the_spelling() -> None:
    for name in ("OZON.RU", "Озон", "WILDBERRIES RU", "Яндекс Маркет"):
        assert is_marketplace(name), name
    assert not is_marketplace("Пятёрочка")


async def test_marketplace_is_marked_on_first_meeting(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    payee = await _payees(db_session).ensure(ledger["user"], "OZON.RU")
    assert payee.varied_categories is True


async def test_varied_payee_does_not_learn_a_category(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend_at(db_session, ledger, "Ozon")
    payee = await _payees(db_session).ensure(ledger["user"], "Ozon")
    assert payee.last_category_id is None


async def test_ordinary_shop_still_learns(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    category = await _spend_at(db_session, ledger, "Гудвин")
    payee = await _payees(db_session).ensure(ledger["user"], "Гудвин")
    assert payee.varied_categories is False
    assert payee.last_category_id == category


async def test_marking_varied_forgets_what_was_learnt(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend_at(db_session, ledger, "Гудвин")
    service = _payees(db_session)
    payee = await service.ensure(ledger["user"], "Гудвин")
    payee = await service.update_payee(
        payee.id, ledger["user"], PayeeUpdate(varied_categories=True)
    )
    assert payee.varied_categories is True
    assert payee.last_category_id is None
