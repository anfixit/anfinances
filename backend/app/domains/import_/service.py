"""Бизнес-логика домена import_.

Массовый импорт транзакций (через TransactionService — те же
правила: знак, amount_rub, валидация) и восстановление полного
бэкапа в пустой аккаунт.

Восстановление перегенерирует UUID и ремапит все ссылки
(parent_id, account_id, category_id, transfer_id, payee_id,
credit_id, transaction_id), чтобы не было конфликтов первичных
ключей при заливке в ту же БД. user_id всех строк = текущий юзер.
Профильные настройки (имя, часовой пояс, валюта по умолчанию,
локаль) берутся из бэкапа; email/пароль не трогаются.
"""

import uuid
from collections.abc import Sequence

from app.core.exceptions import AlreadyExistsError, ValidationFailedError
from app.domains.accounts.models import Account
from app.domains.budgets.models import Budget
from app.domains.categories.models import Category
from app.domains.credits.models import Credit, CreditPayment
from app.domains.currencies.models import UserCurrency
from app.domains.export.schemas import ExportBundle
from app.domains.goals.models import CategoryGoal
from app.domains.import_.repository import ImportRepository
from app.domains.import_.schemas import ImportResult
from app.domains.payees.models import Payee
from app.domains.payees.service import payee_key
from app.domains.reconciliation.models import Reconciliation
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

        accounts = {a.id: uuid.uuid4() for a in bundle.accounts}
        categories = {c.id: uuid.uuid4() for c in bundle.categories}
        transfers = {t.id: uuid.uuid4() for t in bundle.transfers}
        # Новые id операций нужны заранее: на них ссылаются платежи по
        # кредиту и корректировки сверок.
        transactions = {t.id: uuid.uuid4() for t in bundle.transactions}
        credits = {c.id: uuid.uuid4() for c in bundle.credits}
        payees = {p.id: uuid.uuid4() for p in bundle.payees}

        objects: list[object] = []
        for account in bundle.accounts:
            objects.append(
                Account(
                    id=accounts[account.id],
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
            objects.append(
                Category(
                    id=categories[category.id],
                    user_id=user_id,
                    parent_id=_remap(categories, category.parent_id),
                    name=category.name,
                    icon=category.icon,
                    kind=category.kind,
                    is_archived=category.is_archived,
                    sort_order=category.sort_order,
                )
            )
        for payee in bundle.payees:
            objects.append(
                Payee(
                    id=payees[payee.id],
                    user_id=user_id,
                    name=payee.name,
                    # Ключ пересчитываем, а не берём из файла: правила
                    # нормализации могли поменяться со дня бэкапа.
                    name_key=payee_key(payee.name),
                    last_category_id=_remap(
                        categories, payee.last_category_id
                    ),
                    varied_categories=payee.varied_categories,
                )
            )
        for transfer in bundle.transfers:
            objects.append(
                Transfer(id=transfers[transfer.id], user_id=user_id)
            )
        for tx in bundle.transactions:
            objects.append(
                Transaction(
                    id=transactions[tx.id],
                    user_id=user_id,
                    transfer_id=_remap(transfers, tx.transfer_id),
                    date=tx.date,
                    kind=tx.kind,
                    required=tx.required,
                    amount=tx.amount,
                    currency_code=tx.currency_code,
                    amount_rub=tx.amount_rub,
                    exchange_rate=tx.exchange_rate,
                    account_id=accounts[tx.account_id],
                    category_id=_remap(categories, tx.category_id),
                    payee_id=_remap(payees, tx.payee_id),
                    payee_name_snapshot=tx.payee_name_snapshot,
                    category_name_snapshot=tx.category_name_snapshot,
                    subcategory_name_snapshot=tx.subcategory_name_snapshot,
                    account_name_snapshot=tx.account_name_snapshot,
                    to_account_name_snapshot=tx.to_account_name_snapshot,
                    comment=tx.comment,
                    reconciled_at=tx.reconciled_at,
                )
            )
        for credit in bundle.credits:
            objects.append(
                Credit(
                    id=credits[credit.id],
                    user_id=user_id,
                    name=credit.name,
                    lender=credit.lender,
                    currency_code=credit.currency_code,
                    principal_initial=credit.principal_initial,
                    principal_balance=credit.principal_balance,
                    annual_rate=credit.annual_rate,
                    term_months=credit.term_months,
                    monthly_payment=credit.monthly_payment,
                    start_date=credit.start_date,
                    payment_day=credit.payment_day,
                    linked_account_id=_remap(
                        accounts, credit.linked_account_id
                    ),
                    comments=credit.comments,
                    is_archived=credit.is_archived,
                )
            )
        for payment in bundle.credit_payments:
            objects.append(
                CreditPayment(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    credit_id=credits[payment.credit_id],
                    payment_account_id=accounts[payment.payment_account_id],
                    transaction_id=_remap(
                        transactions, payment.transaction_id
                    ),
                    date=payment.date,
                    total_amount=payment.total_amount,
                    principal_amount=payment.principal_amount,
                    interest_amount=payment.interest_amount,
                    fee_amount=payment.fee_amount,
                    currency_code=payment.currency_code,
                    interest_category_id=_remap(
                        categories, payment.interest_category_id
                    ),
                    fee_category_id=_remap(
                        categories, payment.fee_category_id
                    ),
                    comment=payment.comment,
                )
            )
        for goal in bundle.goals:
            objects.append(
                CategoryGoal(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    category_id=categories[goal.category_id],
                    kind=goal.kind,
                    amount=goal.amount,
                    target_date=goal.target_date,
                )
            )
        for reconciliation in bundle.reconciliations:
            objects.append(
                Reconciliation(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    account_id=accounts[reconciliation.account_id],
                    date=reconciliation.date,
                    statement_balance=reconciliation.statement_balance,
                    computed_balance=reconciliation.computed_balance,
                    adjustment_transaction_id=_remap(
                        transactions, reconciliation.adjustment_transaction_id
                    ),
                )
            )
        for budget in bundle.budgets:
            objects.append(
                Budget(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    month=budget.month,
                    category_id=categories[budget.category_id],
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
                    category_id=categories[item.category_id],
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
            credits=len(bundle.credits),
            credit_payments=len(bundle.credit_payments),
            payees=len(bundle.payees),
            goals=len(bundle.goals),
            reconciliations=len(bundle.reconciliations),
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


def _remap(
    mapping: dict[uuid.UUID, uuid.UUID], value: uuid.UUID | None
) -> uuid.UUID | None:
    """Старый id → новый; пустая ссылка остаётся пустой."""
    return None if value is None else mapping[value]


def _check_currencies(bundle: ExportBundle, existing: set[str]) -> None:
    used = {a.currency_code for a in bundle.accounts}
    used |= {t.currency_code for t in bundle.transactions}
    used |= {
        r.currency_code
        for r in bundle.recurring
        if r.currency_code is not None
    }
    used |= {c.currency_code for c in bundle.currencies}
    used |= {c.currency_code for c in bundle.credits}
    used |= {p.currency_code for p in bundle.credit_payments}
    missing = used - existing
    if missing:
        codes = ", ".join(sorted(missing))
        raise ValidationFailedError(f"В справочнике валют нет: {codes}.")


def _check_integrity(bundle: ExportBundle) -> None:
    """Каждая ссылка в бэкапе должна вести на запись из того же бэкапа.

    Иначе восстановление упало бы на KeyError посреди заливки — или,
    хуже, на внешнем ключе уже после частичной записи.
    """
    accounts = {a.id for a in bundle.accounts}
    categories = {c.id for c in bundle.categories}
    transfers = {t.id for t in bundle.transfers}
    transactions = {t.id for t in bundle.transactions}
    credits = {c.id for c in bundle.credits}
    payees = {p.id for p in bundle.payees}

    def need(value: uuid.UUID | None, known: set[uuid.UUID]) -> None:
        if value is not None and value not in known:
            raise ValidationFailedError(_BROKEN)

    for category in bundle.categories:
        need(category.parent_id, categories)
    for payee in bundle.payees:
        need(payee.last_category_id, categories)
    for tx in bundle.transactions:
        need(tx.account_id, accounts)
        need(tx.category_id, categories)
        need(tx.transfer_id, transfers)
        need(tx.payee_id, payees)
    for budget in bundle.budgets:
        need(budget.category_id, categories)
    for item in bundle.recurring:
        need(item.category_id, categories)
    for credit in bundle.credits:
        need(credit.linked_account_id, accounts)
    for payment in bundle.credit_payments:
        need(payment.credit_id, credits)
        need(payment.payment_account_id, accounts)
        need(payment.transaction_id, transactions)
        need(payment.interest_category_id, categories)
        need(payment.fee_category_id, categories)
    for goal in bundle.goals:
        need(goal.category_id, categories)
    for reconciliation in bundle.reconciliations:
        need(reconciliation.account_id, accounts)
        need(reconciliation.adjustment_transaction_id, transactions)


_BROKEN = "Повреждённый бэкап: ссылка на несуществующую запись."
