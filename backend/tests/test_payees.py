"""Получатели: справочник, память категории и отчёт.

Проверяется на настоящей сессии: уникальность по свёрнутому регистру
и агрегат по получателям — это SQL, а не питон, и заглушка про них
ничего не докажет.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.domains.categories.models import Category
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.service import PayeeService
from app.domains.transactions.models import Transaction

WHEN = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
MONTH_FROM = datetime(2026, 8, 1, tzinfo=UTC)
MONTH_TO = datetime(2026, 9, 1, tzinfo=UTC)


def _service(db_session: AsyncSession) -> PayeeService:
    return PayeeService(SqlPayeeRepository(db_session))


async def _category(
    db_session: AsyncSession, user_id: uuid.UUID, name: str
) -> Category:
    category = Category(user_id=user_id, name=name, kind=CategoryKind.EXPENSE)
    db_session.add(category)
    await db_session.flush()
    return category


async def _spend(
    db_session: AsyncSession,
    ledger: dict[str, uuid.UUID],
    payee_id: uuid.UUID | None,
    amount: Decimal,
    when: datetime = WHEN,
    kind: TransactionKind = TransactionKind.EXPENSE,
) -> Transaction:
    signed = -abs(amount) if kind == TransactionKind.EXPENSE else abs(amount)
    tx = Transaction(
        user_id=ledger["user"],
        account_id=ledger["rub"],
        kind=kind,
        amount=signed,
        currency_code="RUB",
        amount_rub=signed,
        exchange_rate=Decimal(1),
        date=when,
        payee_id=payee_id,
    )
    db_session.add(tx)
    await db_session.flush()
    return tx


async def test_same_name_in_another_case_is_one_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """В выписках регистр пляшет, а магазин один."""
    service = _service(db_session)
    first = await service.ensure(ledger["user"], "Пятёрочка")
    second = await service.ensure(ledger["user"], "ПЯТЕРОЧКА")
    assert first.id != second.id, "«е» и «ё» — разные буквы, это разные имена"

    third = await service.ensure(ledger["user"], "пятёрочка")
    assert third.id == first.id


async def test_surrounding_spaces_do_not_make_a_new_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    first = await service.ensure(ledger["user"], "Лента")
    again = await service.ensure(ledger["user"], "  Лента  ")
    assert again.id == first.id
    assert again.name == "Лента"


async def test_duplicate_name_is_refused_on_explicit_create(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    await service.ensure(ledger["user"], "Озон")
    with pytest.raises(AlreadyExistsError):
        await service.create_payee(ledger["user"], _create("ОЗОН"))


def _create(name: str):  # type: ignore[no-untyped-def]
    from app.domains.payees.schemas import PayeeCreate  # noqa: PLC0415

    return PayeeCreate(name=name)


async def test_rename_onto_an_existing_name_is_refused(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Переименование в занятое имя — это слияние, а не правка."""
    from app.domains.payees.schemas import PayeeUpdate  # noqa: PLC0415

    service = _service(db_session)
    await service.ensure(ledger["user"], "Wildberries")
    other = await service.ensure(ledger["user"], "WB")
    with pytest.raises(AlreadyExistsError):
        await service.update_payee(
            other.id, ledger["user"], PayeeUpdate(name="wildberries")
        )


async def test_merge_moves_transactions_and_drops_the_source(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Один магазин под двумя именами из разных выписок."""
    service = _service(db_session)
    source = await service.ensure(ledger["user"], "WILDBERRIES RU")
    target = await service.ensure(ledger["user"], "Wildberries")
    tx = await _spend(db_session, ledger, source.id, Decimal("1200"))

    moved = await service.merge_payees(source.id, target.id, ledger["user"])
    await db_session.flush()

    assert moved == 1
    await db_session.refresh(tx)
    assert tx.payee_id == target.id
    with pytest.raises(NotFoundError):
        await service.get_payee(source.id, ledger["user"])


async def test_merge_carries_the_category_hint_when_target_has_none(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    category = await _category(db_session, ledger["user"], "Одежда")
    source = await service.ensure(ledger["user"], "WB RU")
    source.last_category_id = category.id
    target = await service.ensure(ledger["user"], "WB")

    await service.merge_payees(source.id, target.id, ledger["user"])
    assert target.last_category_id == category.id


async def test_spending_groups_by_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)
    shop = await service.ensure(ledger["user"], "Пятёрочка")
    taxi = await service.ensure(ledger["user"], "Яндекс Go")
    await _spend(db_session, ledger, shop.id, Decimal("500"))
    await _spend(db_session, ledger, shop.id, Decimal("300"))
    await _spend(db_session, ledger, taxi.id, Decimal("250"))

    rows = await repo.spending_by_payee(ledger["user"], MONTH_FROM, MONTH_TO)
    by_name = {row[1]: (row[2], row[3]) for row in rows}
    assert by_name["Пятёрочка"] == (Decimal("800"), 2)
    assert by_name["Яндекс Go"] == (Decimal("250"), 1)


async def test_income_does_not_land_in_payee_spending(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Отчёт про то, кому ушли деньги, а не про то, кто их принёс."""
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)
    payer = await service.ensure(ledger["user"], "Заказчик")
    await _spend(
        db_session,
        ledger,
        payer.id,
        Decimal("50000"),
        kind=TransactionKind.INCOME,
    )

    rows = await repo.spending_by_payee(ledger["user"], MONTH_FROM, MONTH_TO)
    assert rows == []


async def test_new_payees_are_judged_by_the_first_operation(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Выписку заносят задним числом: запись сегодня, трата — нет."""
    service = _service(db_session)
    now = datetime(2026, 8, 22, tzinfo=UTC)
    fresh = await service.ensure(ledger["user"], "Новый сервис")
    old = await service.ensure(ledger["user"], "Старый магазин")
    await _spend(
        db_session,
        ledger,
        fresh.id,
        Decimal("100"),
        when=now - timedelta(days=3),
    )
    await _spend(
        db_session,
        ledger,
        old.id,
        Decimal("100"),
        when=now - timedelta(days=400),
    )

    names = [p.name for p, _ in await service.new_payees(ledger["user"], now)]
    assert names == ["Новый сервис"]


async def test_payee_without_operations_is_not_new(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Заведённый вручную и ни разу не использованный — не событие."""
    service = _service(db_session)
    await service.ensure(ledger["user"], "Просто запись")
    rows = await service.new_payees(
        ledger["user"], datetime(2026, 8, 22, tzinfo=UTC)
    )
    assert rows == []
