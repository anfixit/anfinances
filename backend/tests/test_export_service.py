"""Юнит-тесты ExportService на фейковом репозитории.

Используют лёгкие объекты-заглушки (SimpleNamespace) — схемам и
сервису достаточно нужных атрибутов (from_attributes читает по
именам). Покрывают бэкап, CSV (имена, русские подписи, знак суммы,
BOM), фильтр по датам, XLSX и пустую категорию у перевода.
"""

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.core.enums import (
    AccountType,
    CategoryKind,
    RequiredKind,
    TransactionKind,
)
from app.core.exceptions import NotFoundError
from app.domains.export.service import ExportService

USER = uuid.uuid4()
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class FakeExportRepo:
    def __init__(self) -> None:
        self.user: object | None = None
        self.currencies: list[object] = []
        self.accounts: list[object] = []
        self.categories: list[object] = []
        self.transfers: list[object] = []
        self.transactions: list[object] = []
        self.budgets: list[object] = []
        self.recurring: list[object] = []

    async def get_user(self, user_id):
        return self.user

    async def list_user_currencies(self, user_id):
        return self.currencies

    async def list_accounts(self, user_id):
        return self.accounts

    async def list_categories(self, user_id):
        return self.categories

    async def list_transfers(self, user_id):
        return self.transfers

    async def list_transactions(self, user_id, date_from, date_to):
        out = self.transactions
        if date_from is not None:
            out = [t for t in out if t.date >= date_from]
        if date_to is not None:
            out = [t for t in out if t.date < date_to]
        return out

    async def list_budgets(self, user_id):
        return self.budgets

    async def list_recurring(self, user_id):
        return self.recurring


def _user():
    return SimpleNamespace(
        id=USER,
        email="a@b.com",
        name="Аня",
        timezone="Europe/Moscow",
        default_currency="RUB",
        locale="ru",
        is_active=True,
        is_verified=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _account(name="Карта", acc_id=None):
    return SimpleNamespace(
        id=acc_id or uuid.uuid4(),
        name=name,
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


def _category(name="Еда", cat_id=None):
    return SimpleNamespace(
        id=cat_id or uuid.uuid4(),
        parent_id=None,
        name=name,
        icon=None,
        kind=CategoryKind.EXPENSE,
        is_archived=False,
        sort_order=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _tx(account_id, category_id, *, kind, amount, when=NOW):
    return SimpleNamespace(
        id=uuid.uuid4(),
        transfer_id=None,
        date=when,
        kind=kind,
        required=RequiredKind.REQUIRED,
        amount=Decimal(amount),
        currency_code="RUB",
        amount_rub=Decimal(amount),
        exchange_rate=Decimal("1"),
        account_id=account_id,
        category_id=category_id,
        comment="кофе",
        created_at=NOW,
        updated_at=NOW,
    )


def _service_with_basic() -> tuple[ExportService, FakeExportRepo, dict]:
    repo = FakeExportRepo()
    repo.user = _user()
    acc = _account()
    cat = _category()
    repo.accounts = [acc]
    repo.categories = [cat]
    return ExportService(repo), repo, {"acc": acc, "cat": cat}


async def test_build_backup_structure() -> None:
    svc, repo, ref = _service_with_basic()
    repo.transactions = [
        _tx(
            ref["acc"].id,
            ref["cat"].id,
            kind=TransactionKind.EXPENSE,
            amount="-300",
        )
    ]
    bundle = await svc.build_backup(USER)
    assert bundle.version == 1
    assert bundle.user.email == "a@b.com"
    assert len(bundle.accounts) == 1
    assert len(bundle.transactions) == 1
    assert bundle.transactions[0].amount == Decimal("-300")
    # сериализуется в JSON без ошибок, суммы — строками (§ARCHITECTURE)
    payload = json.loads(await svc.build_backup_json(USER))
    amount = payload["transactions"][0]["amount"]
    assert isinstance(amount, str)
    assert Decimal(amount) == Decimal("-300")
    assert Decimal(payload["accounts"][0]["initial_balance"]) == 0


async def test_backup_missing_user() -> None:
    svc = ExportService(FakeExportRepo())
    with pytest.raises(NotFoundError):
        await svc.build_backup(uuid.uuid4())


async def test_transactions_csv_human_readable() -> None:
    svc, repo, ref = _service_with_basic()
    repo.transactions = [
        _tx(
            ref["acc"].id,
            ref["cat"].id,
            kind=TransactionKind.EXPENSE,
            amount="-300",
        )
    ]
    content = await svc.transactions_csv(USER, None, None)
    assert content.startswith("\ufeff")  # BOM для Excel
    rows = list(csv.reader(io.StringIO(content.lstrip("\ufeff"))))
    assert rows[0] == [
        "Дата",
        "Счёт",
        "Категория",
        "Тип",
        "Обязательность",
        "Сумма",
        "Валюта",
        "Сумма в рублях",
        "Комментарий",
    ]
    assert rows[1][1] == "Карта"  # имя счёта, не UUID
    assert rows[1][2] == "Еда"  # имя категории
    assert rows[1][3] == "Расход"  # тип по-русски
    assert rows[1][5] == "-300"  # знак сохранён


async def test_csv_respects_date_filter() -> None:
    svc, repo, ref = _service_with_basic()
    jan = datetime(2026, 1, 10, tzinfo=UTC)
    mar = datetime(2026, 3, 10, tzinfo=UTC)
    repo.transactions = [
        _tx(
            ref["acc"].id,
            ref["cat"].id,
            kind=TransactionKind.EXPENSE,
            amount="-100",
            when=jan,
        ),
        _tx(
            ref["acc"].id,
            ref["cat"].id,
            kind=TransactionKind.EXPENSE,
            amount="-200",
            when=mar,
        ),
    ]
    content = await svc.transactions_csv(
        USER, datetime(2026, 2, 1, tzinfo=UTC), None
    )
    rows = list(csv.reader(io.StringIO(content.lstrip("\ufeff"))))
    assert len(rows) == 2  # заголовок + 1 (мартовская)
    assert rows[1][5] == "-200"


async def test_transfer_leg_has_blank_category() -> None:
    svc, repo, ref = _service_with_basic()
    leg = _tx(
        ref["acc"].id, None, kind=TransactionKind.TRANSFER, amount="-500"
    )
    repo.transactions = [leg]
    content = await svc.transactions_csv(USER, None, None)
    rows = list(csv.reader(io.StringIO(content.lstrip("\ufeff"))))
    assert rows[1][2] == ""  # категория пустая
    assert rows[1][3] == "Перевод"


async def test_transactions_xlsx_loads() -> None:
    svc, repo, ref = _service_with_basic()
    repo.transactions = [
        _tx(
            ref["acc"].id,
            ref["cat"].id,
            kind=TransactionKind.EXPENSE,
            amount="-300",
        )
    ]
    raw = await svc.transactions_xlsx(USER, None, None)
    wb = load_workbook(io.BytesIO(raw))
    sheet = wb.active
    assert sheet.title == "Транзакции"
    header = [c.value for c in sheet[1]]
    assert header[0] == "Дата"
    row = [c.value for c in sheet[2]]
    assert row[1] == "Карта"
    assert row[5] == -300.0  # сумма числом
