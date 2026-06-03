"""Бизнес-логика домена export.

Выгрузка транзакций в CSV/XLSX (по-человечески: имена счёта и
категории, русские подписи, знак суммы сохранён) и полный бэкап в
JSON. Read-only: ничего не меняет.
"""

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from openpyxl import Workbook

from app.core.enums import RequiredKind, TransactionKind
from app.core.exceptions import NotFoundError
from app.domains.export.repository import ExportRepository
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

__all__ = ["ExportService"]

_KIND_RU = {
    TransactionKind.EXPENSE: "Расход",
    TransactionKind.INCOME: "Доход",
    TransactionKind.TRANSFER: "Перевод",
}
_REQUIRED_RU = {
    RequiredKind.REQUIRED: "Обязательно",
    RequiredKind.OPTIONAL: "Необязательно",
}
# (ключ записи, подпись колонки)
_COLUMNS = (
    ("date", "Дата"),
    ("account", "Счёт"),
    ("category", "Категория"),
    ("kind", "Тип"),
    ("required", "Обязательность"),
    ("amount", "Сумма"),
    ("currency", "Валюта"),
    ("amount_rub", "Сумма в рублях"),
    ("comment", "Комментарий"),
)
_NUMERIC_KEYS = frozenset({"amount", "amount_rub"})


class ExportService:
    def __init__(self, repo: ExportRepository) -> None:
        self._repo = repo

    async def build_backup(self, user_id: uuid.UUID) -> ExportBundle:
        user = await self._repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден.")
        currencies = await self._repo.list_user_currencies(user_id)
        accounts = await self._repo.list_accounts(user_id)
        categories = await self._repo.list_categories(user_id)
        transfers = await self._repo.list_transfers(user_id)
        transactions = await self._repo.list_transactions(user_id, None, None)
        budgets = await self._repo.list_budgets(user_id)
        recurring = await self._repo.list_recurring(user_id)
        return ExportBundle(
            version=1,
            exported_at=datetime.now(UTC),
            user=ExportUser.model_validate(user),
            currencies=[
                ExportUserCurrency.model_validate(c) for c in currencies
            ],
            accounts=[ExportAccount.model_validate(a) for a in accounts],
            categories=[ExportCategory.model_validate(c) for c in categories],
            transfers=[ExportTransfer.model_validate(t) for t in transfers],
            transactions=[
                ExportTransaction.model_validate(t) for t in transactions
            ],
            budgets=[ExportBudget.model_validate(b) for b in budgets],
            recurring=[ExportRecurring.model_validate(r) for r in recurring],
        )

    async def build_backup_json(self, user_id: uuid.UUID) -> str:
        bundle = await self.build_backup(user_id)
        return bundle.model_dump_json(indent=2)

    async def transactions_csv(
        self,
        user_id: uuid.UUID,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> str:
        records = await self._records(user_id, date_from, date_to)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([label for _, label in _COLUMNS])
        for record in records:
            writer.writerow([_csv_cell(record[key]) for key, _ in _COLUMNS])
        # BOM — чтобы Excel корректно открыл кириллицу в UTF-8.
        return "\ufeff" + buffer.getvalue()

    async def transactions_xlsx(
        self,
        user_id: uuid.UUID,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> bytes:
        records = await self._records(user_id, date_from, date_to)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Транзакции"
        sheet.append([label for _, label in _COLUMNS])
        for record in records:
            sheet.append([_xlsx_cell(key, record[key]) for key, _ in _COLUMNS])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    async def _records(
        self,
        user_id: uuid.UUID,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[dict[str, object]]:
        accounts = await self._repo.list_accounts(user_id)
        categories = await self._repo.list_categories(user_id)
        account_names = {a.id: a.name for a in accounts}
        category_names = {c.id: c.name for c in categories}
        transactions = await self._repo.list_transactions(
            user_id, date_from, date_to
        )
        records: list[dict[str, object]] = []
        for tx in transactions:
            category = ""
            if tx.category_id is not None:
                category = category_names.get(tx.category_id, "")
            records.append(
                {
                    "date": tx.date.strftime("%Y-%m-%d"),
                    "account": account_names.get(tx.account_id, ""),
                    "category": category,
                    "kind": _KIND_RU.get(tx.kind, str(tx.kind)),
                    "required": _REQUIRED_RU.get(tx.required, ""),
                    "amount": tx.amount,
                    "currency": tx.currency_code,
                    "amount_rub": tx.amount_rub,
                    "comment": tx.comment or "",
                }
            )
        return records


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _xlsx_cell(key: str, value: object) -> object:
    if value is None:
        return ""
    if key in _NUMERIC_KEYS and isinstance(value, Decimal):
        return float(value)
    return value
