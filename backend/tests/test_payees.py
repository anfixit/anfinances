"""Получатели: справочник, память категории и отчёт.

Проверяется на настоящей сессии: уникальность по свёрнутому регистру
и агрегат по получателям — это SQL, а не питон, и заглушка про них
ничего не докажет.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.domains.categories.models import Category
from app.domains.payees.models import Payee
from app.domains.payees.repository import SqlPayeeRepository
from app.domains.payees.schemas import PayeeCreate
from app.domains.payees.service import PayeeService
from app.domains.transactions.models import Transaction

WHEN = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
MONTH_FROM = datetime(2026, 8, 1, tzinfo=UTC)
MONTH_TO = datetime(2026, 9, 1, tzinfo=UTC)


def _service(db_session: AsyncSession) -> PayeeService:
    return PayeeService(SqlPayeeRepository(db_session))


async def _confirmed(
    service: PayeeService, ledger: dict[str, uuid.UUID], name: str
) -> Payee:
    """Подтверждённый получатель: сам из операции он больше не заводится."""
    return await service.create_payee(ledger["user"], PayeeCreate(name=name))


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
    snapshot: str | None = None,
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
        payee_name_snapshot=snapshot,
    )
    db_session.add(tx)
    await db_session.flush()
    return tx


async def test_same_name_in_another_case_is_one_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """В выписках регистр пляшет, а магазин один."""
    service = _service(db_session)
    first = await _confirmed(service, ledger, "Пятёрочка")
    other, _ = await service.remember(ledger["user"], "ПЯТЕРОЧКА")
    assert other is None, "«е» и «ё» — разные буквы, это разные имена"

    third, _ = await service.remember(ledger["user"], "пятёрочка")
    assert third is not None
    assert third.id == first.id


async def test_surrounding_spaces_do_not_make_a_new_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    first = await _confirmed(service, ledger, "Лента")
    again, name = await service.remember(ledger["user"], "  Лента  ")
    assert again is not None
    assert again.id == first.id
    assert name == "Лента"


async def test_duplicate_name_is_refused_on_explicit_create(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    await _confirmed(service, ledger, "Озон")
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
    await _confirmed(service, ledger, "Wildberries")
    other = await _confirmed(service, ledger, "WB")
    with pytest.raises(AlreadyExistsError):
        await service.update_payee(
            other.id, ledger["user"], PayeeUpdate(name="wildberries")
        )


async def test_merge_moves_transactions_and_drops_the_source(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Один магазин под двумя именами из разных выписок."""
    service = _service(db_session)
    source = await _confirmed(service, ledger, "WILDBERRIES RU")
    target = await _confirmed(service, ledger, "Wildberries")
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
    source = await _confirmed(service, ledger, "WB RU")
    source.last_category_id = category.id
    target = await _confirmed(service, ledger, "WB")

    await service.merge_payees(source.id, target.id, ledger["user"])
    assert target.last_category_id == category.id


async def test_spending_groups_by_payee(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)
    shop = await _confirmed(service, ledger, "Пятёрочка")
    taxi = await _confirmed(service, ledger, "Яндекс Go")
    await _spend(db_session, ledger, shop.id, Decimal("500"))
    await _spend(db_session, ledger, shop.id, Decimal("300"))
    await _spend(db_session, ledger, taxi.id, Decimal("250"))

    rows = await repo.spending_by_payee(ledger["user"], MONTH_FROM, MONTH_TO)
    by_name = {row[1]: (row[2], row[3]) for row in rows}
    assert by_name["Пятёрочка"] == (Decimal("800"), 2)
    assert by_name["Яндекс Go"] == (Decimal("250"), 1)


async def test_spending_counts_unsorted_names_separately(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Ждущие имена не в строках отчёта, но их число и сумма видны."""
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)
    shop = await _confirmed(service, ledger, "Пятёрочка")
    await _spend(db_session, ledger, shop.id, Decimal("500"))
    await _spend(db_session, ledger, None, Decimal("300"), snapshot="Кофейня")
    # То же имя в другом написании и вторая операция: имя одно.
    await _spend(
        db_session, ledger, None, Decimal("100"), snapshot="  КОФЕЙНЯ "
    )
    await _spend(db_session, ledger, None, Decimal("700"), snapshot="Аптека")
    # Не считаются: другой месяц, доход, пустой снимок.
    await _spend(
        db_session,
        ledger,
        None,
        Decimal("9"),
        when=datetime(2026, 7, 15, tzinfo=UTC),
        snapshot="Старое",
    )
    await _spend(
        db_session,
        ledger,
        None,
        Decimal("9000"),
        kind=TransactionKind.INCOME,
        snapshot="Заказчик",
    )
    await _spend(db_session, ledger, None, Decimal("5"), snapshot="")

    rows = await repo.spending_by_payee(ledger["user"], MONTH_FROM, MONTH_TO)
    assert [row[1] for row in rows] == ["Пятёрочка"]

    names, amount = await repo.unsorted_spending(
        ledger["user"], MONTH_FROM, MONTH_TO
    )
    assert names == 2
    assert amount == Decimal("1100")


async def test_income_does_not_land_in_payee_spending(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Отчёт про то, кому ушли деньги, а не про то, кто их принёс."""
    service = _service(db_session)
    repo = SqlPayeeRepository(db_session)
    payer = await _confirmed(service, ledger, "Заказчик")
    await _spend(
        db_session,
        ledger,
        payer.id,
        Decimal("50000"),
        kind=TransactionKind.INCOME,
    )

    rows = await repo.spending_by_payee(ledger["user"], MONTH_FROM, MONTH_TO)
    assert rows == []


async def test_uncategorized_filter_skips_transfer_legs(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """У ноги перевода категории нет по определению, разбирать нечего."""
    from app.domains.transactions.models import Transfer  # noqa: PLC0415
    from app.domains.transactions.repository import (  # noqa: PLC0415
        SqlTransactionRepository,
        TransactionFilter,
    )

    transfer = Transfer(user_id=ledger["user"])
    db_session.add(transfer)
    await db_session.flush()

    leg = await _spend(db_session, ledger, None, Decimal("100"))
    leg.transfer_id = transfer.id
    await _spend(db_session, ledger, None, Decimal("250"))
    await db_session.flush()

    rows = await SqlTransactionRepository(db_session).list_page(
        ledger["user"], TransactionFilter(uncategorized=True, limit=50)
    )
    assert [abs(r.amount) for r in rows] == [Decimal("250")]
