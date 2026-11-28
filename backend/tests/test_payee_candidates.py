"""Кандидаты в получатели: таблица и доступ к ней.

Проверяется на настоящей сессии: уникальность по свёрнутому имени —
это индекс БД, а ключ считает питон, и заглушка про это ничего не
докажет.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.domains.accounts.repository import SqlAccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import SqlCategoryRepository
from app.domains.payees.models import Payee, PayeeCandidate
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.schemas import PayeeCreate
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
    amount: Decimal = Decimal("500"),
    when: datetime = WHEN,
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
            amount=amount,
            date=when,
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


def _service(db_session: AsyncSession) -> PayeeService:
    return PayeeService(SqlPayeeRepository(db_session))


async def _category(
    db_session: AsyncSession, user_id: uuid.UUID, name: str
) -> Category:
    category = Category(user_id=user_id, name=name, kind=CategoryKind.EXPENSE)
    db_session.add(category)
    await db_session.flush()
    return category


async def _only_candidate(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID], name: str
) -> PayeeCandidate:
    found = await SqlPayeeRepository(db_session).get_candidate(
        ledger["user"], payee_key(name)
    )
    assert found is not None
    return found


async def test_accept_moves_earlier_operations(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    txs = [await _spend(db_session, ledger, "Аптека Вита") for _ in range(3)]
    candidate = await _only_candidate(db_session, ledger, "Аптека Вита")

    payee = await _service(db_session).accept_candidate(
        candidate.id, ledger["user"], None
    )

    assert payee.name == "Аптека Вита"
    assert [t.payee_id for t in txs] == [payee.id] * 3
    repo = SqlPayeeRepository(db_session)
    assert await repo.get_candidate(ledger["user"], candidate.name_key) is None


async def test_accept_seeds_the_category_hint(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    old = await _category(db_session, ledger["user"], "Лекарства")
    fresh = await _category(db_session, ledger["user"], "Здоровье")
    await _spend(
        db_session,
        ledger,
        "Аптека Вита",
        old.id,
        when=WHEN - timedelta(days=9),
    )
    await _spend(db_session, ledger, "Аптека Вита", fresh.id, when=WHEN)
    await _spend(
        db_session,
        ledger,
        "Аптека Вита",
        old.id,
        when=WHEN - timedelta(days=3),
    )
    candidate = await _only_candidate(db_session, ledger, "Аптека Вита")

    payee = await _service(db_session).accept_candidate(
        candidate.id, ledger["user"], None
    )

    assert payee.last_category_id == fresh.id


async def test_accept_into_an_existing_payee_creates_nothing(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    shop = await service.create_payee(ledger["user"], PayeeCreate(name="Вита"))
    tx = await _spend(db_session, ledger, "Аптека Вита")
    candidate = await _only_candidate(db_session, ledger, "Аптека Вита")

    result = await service.accept_candidate(
        candidate.id, ledger["user"], shop.id
    )

    assert result.id == shop.id
    assert tx.payee_id == shop.id
    assert shop.last_category_id is None, "память чужого получателя не трогаем"
    repo = SqlPayeeRepository(db_session)
    assert [p.name for p in await repo.list_all(ledger["user"])] == ["Вита"]
    assert await repo.get_candidate(ledger["user"], candidate.name_key) is None


async def test_accept_into_a_missing_payee_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend(db_session, ledger, "Аптека Вита")
    candidate = await _only_candidate(db_session, ledger, "Аптека Вита")

    with pytest.raises(NotFoundError):
        await _service(db_session).accept_candidate(
            candidate.id, ledger["user"], uuid.uuid4()
        )


async def test_accept_is_refused_when_the_name_is_already_taken(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend(db_session, ledger, "Аптека Вита")
    candidate = await _only_candidate(db_session, ledger, "Аптека Вита")
    service = _service(db_session)
    await service.create_payee(ledger["user"], PayeeCreate(name="аптека вита"))

    with pytest.raises(AlreadyExistsError):
        await service.accept_candidate(candidate.id, ledger["user"], None)


async def test_unknown_candidate_is_not_found(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    for action in (
        service.accept_candidate(uuid.uuid4(), ledger["user"], None),
        service.reject_candidate(uuid.uuid4(), ledger["user"]),
        service.unreject_candidate(uuid.uuid4(), ledger["user"]),
    ):
        with pytest.raises(NotFoundError):
            await action


async def test_candidate_carries_the_total_of_its_orphan_operations(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _spend(db_session, ledger, "Аптека Вита", amount=Decimal("300"))
    await _spend(db_session, ledger, "аптека  вита", amount=Decimal("200"))
    await _spend(db_session, ledger, "Злата", amount=Decimal("900"))
    await _spend(db_session, ledger, "Мелочь", amount=Decimal("10"))

    rows = await _service(db_session).list_candidates(
        ledger["user"], "pending"
    )

    assert [(c.name, amount) for c, amount in rows] == [
        ("Злата", Decimal("900")),
        ("Аптека Вита", Decimal("500")),
        ("Мелочь", Decimal("10")),
    ]


async def test_total_ignores_operations_of_other_names_and_confirmed_ones(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    await service.create_payee(ledger["user"], PayeeCreate(name="Вита"))
    await _spend(db_session, ledger, "Вита", amount=Decimal("700"))
    await _spend(db_session, ledger, "Аптека Вита", amount=Decimal("40"))

    totals = await SqlPayeeRepository(db_session).candidate_totals(
        ledger["user"], [payee_key("Аптека Вита"), payee_key("Вита")]
    )

    assert totals == {payee_key("Аптека Вита"): Decimal("40")}


async def test_marketplace_candidate_gets_varied_categories(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    category = await _category(db_session, ledger["user"], "Дом")
    tx = await _spend(db_session, ledger, "OZON.RU", category.id)
    candidate = await _only_candidate(db_session, ledger, "OZON.RU")

    payee = await _service(db_session).accept_candidate(
        candidate.id, ledger["user"], None
    )

    assert payee.varied_categories is True
    assert payee.last_category_id is None
    assert tx.payee_id == payee.id


async def test_reject_hides_the_name_and_unreject_returns_it(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    tx = await _spend(db_session, ledger, "Иванов Иван")
    candidate = await _only_candidate(db_session, ledger, "Иванов Иван")
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)

    await service.reject_candidate(candidate.id, ledger["user"])

    assert await repo.list_candidates(ledger["user"], "pending") == []
    declined = await service.list_candidates(ledger["user"], "rejected")
    assert [c.name for c, _ in declined] == ["Иванов Иван"]
    assert tx.payee_name_snapshot == "Иванов Иван"

    await service.unreject_candidate(candidate.id, ledger["user"])

    assert candidate.status == "pending"
    assert await repo.list_candidates(ledger["user"], "rejected") == []


async def test_deleting_a_payee_rejects_the_name(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    shop = await service.create_payee(ledger["user"], PayeeCreate(name="Вита"))
    first = await _spend(db_session, ledger, "Вита")
    second = await _spend(db_session, ledger, "Вита")
    assert first.payee_id == shop.id

    await service.delete_payee(shop.id, ledger["user"])
    await db_session.flush()

    repo = SqlPayeeRepository(db_session)
    assert first.payee_name_snapshot == "Вита"
    assert second.payee_name_snapshot == "Вита"
    kept = await repo.get_candidate(ledger["user"], payee_key("Вита"))
    assert kept is not None
    assert kept.status == "rejected"

    again = await _spend(db_session, ledger, "вита")
    assert again.payee_id is None
    assert again.payee_name_snapshot == "вита"
    assert await repo.list_all(ledger["user"]) == []
    assert await repo.list_candidates(ledger["user"], "pending") == []


async def test_deleting_a_payee_keeps_an_existing_candidate_rejected(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Кандидат с этим ключом уже есть (его завели до подтверждения)."""
    service = _service(db_session)
    shop = await service.create_payee(ledger["user"], PayeeCreate(name="Вита"))
    repo = SqlPayeeRepository(db_session)
    await repo.add_candidate(_candidate(ledger["user"], "Вита"))

    await service.delete_payee(shop.id, ledger["user"])

    kept = await repo.get_candidate(ledger["user"], payee_key("Вита"))
    assert kept is not None
    assert kept.status == "rejected"
