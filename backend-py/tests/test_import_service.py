"""Юнит-тесты ImportService на фейковых репозиториях.

Покрывают массовый импорт транзакций (через фейковый
TransactionService) и восстановление бэкапа: отказ для непустого
аккаунта, проверку валют и целостности, ремап ссылок и счётчики.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.enums import (
    AccountType,
    CategoryKind,
    RequiredKind,
    TransactionKind,
)
from app.core.exceptions import AlreadyExistsError, ValidationFailedError
from app.domains.export.schemas import (
    ExportAccount,
    ExportBudget,
    ExportBundle,
    ExportCategory,
    ExportRecurring,
    ExportTransaction,
    ExportTransfer,
    ExportUser,
    ExportUserCurrency,
)
from app.domains.import_.service import ImportService

USER = uuid.uuid4()
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeImportRepo:
    def __init__(self, has_data: bool = False) -> None:
        self.has_data = has_data
        self.currencies = {"RUB", "USD"}
        self.added: list[object] = []
        self.cleared = False
        self.user = _orm_user()

    async def has_user_data(self, user_id):
        return self.has_data

    async def clear_config(self, user_id):
        self.cleared = True

    async def existing_currency_codes(self):
        return set(self.currencies)

    async def add_all(self, objects):
        self.added.extend(objects)

    async def get_user(self, user_id):
        return self.user


class FakeTransactions:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def create_transaction(self, user_id, data):
        self.calls.append((user_id, data))
        return data


class _OrmUser:
    name = None
    timezone = None
    default_currency = None
    locale = None


def _orm_user() -> _OrmUser:
    return _OrmUser()


# ── Импорт транзакций ────────────────────────────────────────


async def test_import_transactions_runs_each() -> None:
    repo = FakeImportRepo()
    txs = FakeTransactions()
    svc = ImportService(repo, txs)
    count = await svc.import_transactions(USER, ["a", "b", "c"])
    assert count == 3
    assert len(txs.calls) == 3
    assert all(call[0] == USER for call in txs.calls)


# ── Восстановление бэкапа ────────────────────────────────────


def _bundle() -> ExportBundle:
    acc_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    transfer_id = uuid.uuid4()
    return ExportBundle(
        version=1,
        exported_at=NOW,
        user=ExportUser(
            id=uuid.uuid4(),
            email="old@b.com",
            name="Старое имя",
            timezone="Asia/Tashkent",
            default_currency="USD",
            locale="en",
            is_active=True,
            is_verified=True,
            created_at=NOW,
            updated_at=NOW,
        ),
        currencies=[
            ExportUserCurrency(
                id=uuid.uuid4(),
                currency_code="RUB",
                is_default=True,
                sort_order=0,
            )
        ],
        accounts=[
            ExportAccount(
                id=acc_id,
                name="Карта",
                type=AccountType.CARD,
                currency_code="RUB",
                initial_balance=Decimal("0"),
                credit_limit=None,
                color=None,
                sort_order=0,
                comments=None,
                is_archived=False,
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        categories=[
            ExportCategory(
                id=parent_id,
                parent_id=None,
                name="Еда",
                icon=None,
                kind=CategoryKind.EXPENSE,
                is_archived=False,
                sort_order=0,
                created_at=NOW,
                updated_at=NOW,
            ),
            ExportCategory(
                id=child_id,
                parent_id=parent_id,
                name="Продукты",
                icon=None,
                kind=CategoryKind.EXPENSE,
                is_archived=False,
                sort_order=0,
                created_at=NOW,
                updated_at=NOW,
            ),
        ],
        transfers=[ExportTransfer(id=transfer_id, created_at=NOW)],
        transactions=[
            ExportTransaction(
                id=uuid.uuid4(),
                transfer_id=None,
                date=NOW,
                kind=TransactionKind.EXPENSE,
                required=RequiredKind.REQUIRED,
                amount=Decimal("-300"),
                currency_code="RUB",
                amount_rub=Decimal("-300"),
                exchange_rate=Decimal("1"),
                account_id=acc_id,
                category_id=child_id,
                comment=None,
                created_at=NOW,
                updated_at=NOW,
            ),
            ExportTransaction(
                id=uuid.uuid4(),
                transfer_id=transfer_id,
                date=NOW,
                kind=TransactionKind.TRANSFER,
                required=None,
                amount=Decimal("-500"),
                currency_code="RUB",
                amount_rub=Decimal("-500"),
                exchange_rate=Decimal("1"),
                account_id=acc_id,
                category_id=None,
                comment=None,
                created_at=NOW,
                updated_at=NOW,
            ),
        ],
        budgets=[
            ExportBudget(
                id=uuid.uuid4(),
                month=date(2026, 1, 1),
                category_id=parent_id,
                planned=Decimal("10000"),
                notes=None,
                rollover=True,
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        recurring=[
            ExportRecurring(
                id=uuid.uuid4(),
                required=RequiredKind.REQUIRED,
                category_id=child_id,
                name="Продукты",
                monthly_amount=Decimal("8000"),
                currency_code="RUB",
                amount_rub=Decimal("8000"),
                comments=None,
                is_archived=False,
                created_at=NOW,
                updated_at=NOW,
            )
        ],
    )


async def test_restore_rejects_non_empty() -> None:
    svc = ImportService(FakeImportRepo(has_data=True), FakeTransactions())
    with pytest.raises(AlreadyExistsError):
        await svc.restore_all(USER, _bundle())


async def test_restore_missing_currency() -> None:
    repo = FakeImportRepo()
    repo.currencies = {"USD"}  # нет RUB
    svc = ImportService(repo, FakeTransactions())
    with pytest.raises(ValidationFailedError):
        await svc.restore_all(USER, _bundle())


async def test_restore_counts_and_clears() -> None:
    repo = FakeImportRepo()
    svc = ImportService(repo, FakeTransactions())
    result = await svc.restore_all(USER, _bundle())
    assert repo.cleared is True
    assert result.accounts == 1
    assert result.categories == 2
    assert result.transfers == 1
    assert result.transactions == 2
    assert result.budgets == 1
    assert result.recurring == 1
    assert result.currencies == 1
    # всё под текущим юзером
    assert all(o.user_id == USER for o in repo.added)


async def test_restore_remaps_references() -> None:
    repo = FakeImportRepo()
    svc = ImportService(repo, FakeTransactions())
    await svc.restore_all(USER, _bundle())

    accounts = [o for o in repo.added if type(o).__name__ == "Account"]
    categories = [o for o in repo.added if type(o).__name__ == "Category"]
    transfers = [o for o in repo.added if type(o).__name__ == "Transfer"]
    transactions = [o for o in repo.added if type(o).__name__ == "Transaction"]

    new_account_ids = {a.id for a in accounts}
    new_category_ids = {c.id for c in categories}
    new_transfer_ids = {t.id for t in transfers}

    # подкатегория ссылается на новый id родителя
    child = next(c for c in categories if c.parent_id is not None)
    assert child.parent_id in new_category_ids

    # транзакции ссылаются на новые id счёта/категории/перевода
    for tx in transactions:
        assert tx.account_id in new_account_ids
        if tx.category_id is not None:
            assert tx.category_id in new_category_ids
        if tx.transfer_id is not None:
            assert tx.transfer_id in new_transfer_ids


async def test_restore_updates_profile() -> None:
    repo = FakeImportRepo()
    svc = ImportService(repo, FakeTransactions())
    await svc.restore_all(USER, _bundle())
    assert repo.user.timezone == "Asia/Tashkent"
    assert repo.user.default_currency == "USD"
    assert repo.user.name == "Старое имя"


async def test_restore_broken_reference() -> None:
    repo = FakeImportRepo()
    svc = ImportService(repo, FakeTransactions())
    bundle = _bundle()
    # транзакция ссылается на несуществующий счёт
    bundle.transactions[0].account_id = uuid.uuid4()
    with pytest.raises(ValidationFailedError):
        await svc.restore_all(USER, bundle)
