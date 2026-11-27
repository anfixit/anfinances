"""Кандидаты в получатели: таблица и доступ к ней.

Проверяется на настоящей сессии: уникальность по свёрнутому имени —
это индекс БД, а ключ считает питон, и заглушка про это ничего не
докажет.
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
from app.domains.payees.models import Payee, PayeeCandidate
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService, payee_key
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import SqlTransactionRepository
from app.domains.transactions.schemas import TransactionCreate
from app.domains.transactions.service import TransactionService

WHEN = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


def _candidate(user_id: uuid.UUID, name: str) -> PayeeCandidate:
    return PayeeCandidate(
        user_id=user_id,
        name=name,
        name_key=payee_key(name),
        first_seen_at=WHEN,
        last_seen_at=WHEN,
    )


async def test_candidate_is_unique_by_folded_name(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    repo = SqlPayeeRepository(db_session)
    added = await repo.add_candidate(_candidate(ledger["user"], "OZON.RU"))

    found = await repo.get_candidate(ledger["user"], payee_key("ozon.ru"))

    assert found is not None
    assert found.id == added.id
    assert found.name == "OZON.RU"
    assert found.status == "pending"
    assert found.times_seen == 1


async def test_candidate_keeps_a_200_character_name(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    repo = SqlPayeeRepository(db_session)
    name = "Я" * 200
    await repo.add_candidate(_candidate(ledger["user"], name))

    found = await repo.get_candidate(ledger["user"], payee_key(name))

    assert found is not None
    assert found.name == name
    assert len(found.name) == 200


async def test_list_candidates_filters_by_status(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    repo = SqlPayeeRepository(db_session)
    await repo.add_candidate(_candidate(ledger["user"], "Иванов Иван"))
    rejected = _candidate(ledger["user"], "Петров Пётр")
    rejected.status = "rejected"
    await repo.add_candidate(rejected)

    pending = await repo.list_candidates(ledger["user"], "pending")
    declined = await repo.list_candidates(ledger["user"], "rejected")

    assert [c.name for c in pending] == ["Иванов Иван"]
    assert [c.name for c in declined] == ["Петров Пётр"]


class _Currencies:
    async def rate_to_rub(self, code: str) -> Decimal:
        return Decimal(1)


async def _spend(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    payee: str,
    category_id: uuid.UUID | None = None,
) -> Transaction:
    return await TransactionService(
        SqlTransactionRepository(db_session),
        SqlAccountRepository(db_session),
        SqlCategoryRepository(db_session),
        cast(Any, _Currencies()),
        PayeeService(SqlPayeeRepository(db_session)),
    ).create_transaction(
        ledger["user"],
        TransactionCreate(
            account_id=ledger["rub"],
            kind=TransactionKind.EXPENSE,
            amount=Decimal("500"),
            date=WHEN,
            category_id=category_id,
            payee=payee,
        ),
    )


async def test_unknown_name_does_not_create_a_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _spend(db_session, ledger, "Злата")

    repo = SqlPayeeRepository(db_session)
    assert tx.payee_id is None
    assert tx.payee_name_snapshot == "Злата"
    assert await repo.list_all(ledger["user"]) == []
    candidates = await repo.list_candidates(ledger["user"], "pending")
    assert [c.name for c in candidates] == ["Злата"]


async def test_two_spellings_in_one_statement_make_one_candidate(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend(db_session, ledger, "OZON.RU")
    await _spend(db_session, ledger, "Ozon.ru")

    repo = SqlPayeeRepository(db_session)
    candidates = await repo.list_candidates(ledger["user"], "pending")
    assert len(candidates) == 1
    assert candidates[0].times_seen == 2
    assert candidates[0].name == "OZON.RU", (
        "имя остаётся как при первой встрече"
    )


async def test_blank_payee_name_creates_nothing(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = PayeeService(SqlPayeeRepository(db_session))

    payee, name = await service.remember(ledger["user"], "   ")

    repo = SqlPayeeRepository(db_session)
    assert (payee, name) == (None, "")
    assert await repo.list_all(ledger["user"]) == []
    assert await repo.list_candidates(ledger["user"], "pending") == []

    tx = await _spend(db_session, ledger, "   ")
    assert tx.payee_name_snapshot is None
    assert await repo.list_candidates(ledger["user"], "pending") == []


async def test_confirmed_payee_still_resolves(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    category = Category(
        user_id=ledger["user"], name="Продукты", kind=CategoryKind.EXPENSE
    )
    db_session.add(category)
    await db_session.flush()
    repo = SqlPayeeRepository(db_session)
    shop = await repo.add(
        Payee(
            user_id=ledger["user"],
            name="Пятёрочка",
            name_key=payee_key("Пятёрочка"),
        )
    )

    tx = await _spend(db_session, ledger, "ПЯТЁРОЧКА", category.id)

    assert tx.payee_id == shop.id
    assert tx.payee_name_snapshot == "Пятёрочка"
    assert shop.last_category_id == category.id
    assert await repo.list_candidates(ledger["user"], "pending") == []


async def test_rejected_name_does_not_come_back(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    repo = SqlPayeeRepository(db_session)
    declined = _candidate(ledger["user"], "Иванов Иван")
    declined.status = "rejected"
    await repo.add_candidate(declined)

    tx = await _spend(db_session, ledger, "иванов иван")

    assert tx.payee_id is None
    assert tx.payee_name_snapshot == "иванов иван"
    assert await repo.list_candidates(ledger["user"], "pending") == []
    kept = await repo.get_candidate(ledger["user"], payee_key("Иванов Иван"))
    assert kept is not None
    assert kept.status == "rejected"
    assert kept.times_seen == 1
