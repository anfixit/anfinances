"""Кандидаты в получатели: таблица и доступ к ней.

Проверяется на настоящей сессии: уникальность по свёрнутому имени —
это индекс БД, а ключ считает питон, и заглушка про это ничего не
докажет.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.payees.models import PayeeCandidate
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import payee_key

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
