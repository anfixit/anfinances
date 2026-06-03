"""Бизнес-логика домена import_.

Массовый импорт транзакций (через TransactionService — те же
правила: знак, amount_rub, валидация) и восстановление полного
бэкапа в пустой аккаунт.

Восстановление перегенерирует UUID и ремапит все ссылки
(parent_id, account_id, category_id, transfer_id), чтобы не было
конфликтов первичных ключей при заливке в ту же БД. user_id всех
строк = текущий юзер. Профильные настройки (имя, часовой пояс,
валюта по умолчанию, локаль) берутся из бэкапа; email/пароль не
трогаются.
"""

import uuid
from collections.abc import Sequence

from app.core.exceptions import AlreadyExistsError, ValidationFailedError
from app.domains.accounts.models import Account
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.currencies.models import UserCurrency
from app.domains.export.schemas import ExportBundle
from app.domains.import_.repository import ImportRepository
from app.domains.import_.schemas import ImportResult
from app.domains.recurring.models import RecurringExpense
from app.domains.transactions.models import Transaction, Transfer
from app.domains.transactions.schemas import TransactionCreate
from app.domains.transactions.service import TransactionService

__all__ = ["ImportService"]


class ImportService:
    def __init__(
        self,
        repo: ImportRepository,
        transactions: TransactionService,
    ) -> None:
        self._repo = repo
        self._transactions = transactions

    async def import_transactions(
        self, user_id: uuid.UUID, items: Sequence[TransactionCreate]
    ) -> int:
        # Каждая транзакция проходит обычную бизнес-логику сервиса
        # (знак суммы, запекание amount_rub, проверка счёта/категории).
        for data in items:
            await self._transactions.create_transaction(user_id, data)
        return len(items)

    async def restore_all(
        self, user_id: uuid.UUID, bundle: ExportBundle
    ) -> ImportResult:
        if await self._repo.has_user_data(user_id):
            raise AlreadyExistsError(
                "Импорт возможен только в пустой аккаунт. "
                "Удалите существующие счета и транзакции."
            )
        _check_currencies(bundle, await self._repo.existing_currency_codes())
        _check_integrity(bundle)

        await self._repo.clear_config(user_id)

        account_map = {a.id: uuid.uuid4() for a in bundle.accounts}
        category_map = {c.id: uuid.uuid4() for c in bundle.categories}
        transfer_map = {t.id: uuid.uuid4() for t in bundle.transfers}

        objects: list[object] = []
        for account in bundle.accounts:
            objects.append(
                Account(
                    id=account_map[account.id],
                    user_id=user_id,
                    name=account.name,
                    type=account.type,
                    currency_code=account.currency_code,
                    initial_balance=account.initial_balance,
                    credit_limit=account.credit_limit,
                    color=account.color,
                    sort_order=account.sort_order,
                    comments=account.comments,
                    is_archived=account.is_archived,
                )
            )
        for category in bundle.categories:
            parent_id = None
            if category.parent_id is not None:
                parent_id = category_map[category.parent_id]
            objects.append(
                Category(
                    id=category_map[category.id],
                    user_id=user_id,
                    parent_id=parent_id,
                    name=category.name,
                    icon=category.icon,
                    kind=category.kind,
                    is_archived=category.is_archived,
                    sort_order=category.sort_order,
                )
            )
        for transfer in bundle.transfers:
            objects.append(
                Transfer(id=transfer_map[transfer.id], user_id=user_id)
            )
        for tx in bundle.transactions:
            category_id = None
            if tx.category_id is not None:
                category_id = category_map[tx.category_id]
            transfer_id = None
            if tx.transfer_id is not None:
                transfer_id = transfer_map[tx.transfer_id]
            objects.append(
                Transaction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    transfer_id=transfer_id,
                    date=tx.date,
                    kind=tx.kind,
                    required=tx.required,
                    amount=tx.amount,
                    currency_code=tx.currency_code,
                    amount_rub=tx.amount_rub,
                    exchange_rate=tx.exchange_rate,
                    account_id=account_map[tx.account_id],
                    category_id=category_id,
                    comment=tx.comment,
                )
            )
        for budget in bundle.budgets:
            objects.append(
                Budget(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    month=budget.month,
                    category_id=category_map[budget.category_id],
                    planned=budget.planned,
                    notes=budget.notes,
                    rollover=budget.rollover,
                )
            )
        for item in bundle.recurring:
            objects.append(
                RecurringExpense(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    required=item.required,
                    category_id=category_map[item.category_id],
                    name=item.name,
                    monthly_amount=item.monthly_amount,
                    currency_code=item.currency_code,
                    amount_rub=item.amount_rub,
                    comments=item.comments,
                )
            )
        for currency in bundle.currencies:
            objects.append(
                UserCurrency(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    currency_code=currency.currency_code,
                    is_default=currency.is_default,
                    sort_order=currency.sort_order,
                )
            )

        await self._repo.add_all(objects)
        await self._restore_profile(user_id, bundle)

        return ImportResult(
            accounts=len(bundle.accounts),
            categories=len(bundle.categories),
            transfers=len(bundle.transfers),
            transactions=len(bundle.transactions),
            budgets=len(bundle.budgets),
            recurring=len(bundle.recurring),
            currencies=len(bundle.currencies),
        )

    async def _restore_profile(
        self, user_id: uuid.UUID, bundle: ExportBundle
    ) -> None:
        user = await self._repo.get_user(user_id)
        if user is None:
            return
        user.name = bundle.user.name
        user.timezone = bundle.user.timezone
        user.default_currency = bundle.user.default_currency
        user.locale = bundle.user.locale


def _check_currencies(bundle: ExportBundle, existing: set[str]) -> None:
    used = {a.currency_code for a in bundle.accounts}
    used |= {t.currency_code for t in bundle.transactions}
    used |= {
        r.currency_code
        for r in bundle.recurring
        if r.currency_code is not None
    }
    used |= {c.currency_code for c in bundle.currencies}
    missing = used - existing
    if missing:
        codes = ", ".join(sorted(missing))
        raise ValidationFailedError(f"В справочнике валют нет: {codes}.")


def _check_integrity(bundle: ExportBundle) -> None:
    account_ids = {a.id for a in bundle.accounts}
    category_ids = {c.id for c in bundle.categories}
    transfer_ids = {t.id for t in bundle.transfers}

    for category in bundle.categories:
        if (
            category.parent_id is not None
            and category.parent_id not in category_ids
        ):
            raise ValidationFailedError(_BROKEN)
    for tx in bundle.transactions:
        if tx.account_id not in account_ids:
            raise ValidationFailedError(_BROKEN)
        if tx.category_id is not None and tx.category_id not in category_ids:
            raise ValidationFailedError(_BROKEN)
        if tx.transfer_id is not None and tx.transfer_id not in transfer_ids:
            raise ValidationFailedError(_BROKEN)
    for budget in bundle.budgets:
        if budget.category_id not in category_ids:
            raise ValidationFailedError(_BROKEN)
    for item in bundle.recurring:
        if item.category_id not in category_ids:
            raise ValidationFailedError(_BROKEN)


_BROKEN = "Повреждённый бэкап: ссылка на несуществующую запись."
