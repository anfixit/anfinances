"""Бизнес-логика обычных транзакций (расход/доход).

Транзакция всегда в валюте своего счёта. При создании курс
валюты к рублю «запекается» в exchange_rate, а amount_rub
считается на момент операции и далее не пересчитывается при
обновлении курсов (история не плывёт). При правке суммы
amount_rub пересчитывается по уже запечённому курсу.

Удаление физическое: транзакция — это запись операции, а не
справочная сущность, ошибочную проще убрать насовсем.
"""

import uuid

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import (
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.repository import AccountRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import (
    TransactionFilter,
    TransactionRepository,
)
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
)

__all__ = ["TransactionService"]

_KIND_TO_CATEGORY = {
    TransactionKind.EXPENSE: CategoryKind.EXPENSE,
    TransactionKind.INCOME: CategoryKind.INCOME,
}


class TransactionService:
    def __init__(
        self,
        repo: TransactionRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
        currencies: CurrencyService,
    ) -> None:
        self._repo = repo
        self._accounts = accounts
        self._categories = categories
        self._currencies = currencies

    async def list_transactions(
        self, user_id: uuid.UUID, flt: TransactionFilter
    ) -> list[Transaction]:
        return await self._repo.list_page(user_id, flt)

    async def get_transaction(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction:
        tx = await self._repo.get(tx_id, user_id)
        if tx is None:
            raise NotFoundError("Транзакция не найдена.")
        return tx

    async def create_transaction(
        self, user_id: uuid.UUID, data: TransactionCreate
    ) -> Transaction:
        account = await self._accounts.get(data.account_id, user_id)
        if account is None:
            raise NotFoundError("Счёт не найден.")

        await self._validate_category(user_id, data.category_id, data.kind)

        rate = await self._currencies.rate_to_rub(account.currency_code)
        amount_rub = data.amount * rate

        tx = Transaction(
            user_id=user_id,
            account_id=account.id,
            kind=data.kind,
            amount=data.amount,
            currency_code=account.currency_code,
            amount_rub=amount_rub,
            exchange_rate=rate,
            category_id=data.category_id,
            required=data.required,
            date=data.date,
            comment=data.comment,
        )
        return await self._repo.add(tx)

    async def update_transaction(
        self,
        tx_id: uuid.UUID,
        user_id: uuid.UUID,
        data: TransactionUpdate,
    ) -> Transaction:
        tx = await self.get_transaction(tx_id, user_id)
        if tx.transfer_id is not None:
            raise ValidationFailedError(
                "Перевод нельзя править как обычную транзакцию."
            )

        fields = data.model_dump(exclude_unset=True)

        if "category_id" in fields:
            await self._validate_category(
                user_id, fields["category_id"], tx.kind
            )

        for key, value in fields.items():
            setattr(tx, key, value)

        if "amount" in fields:
            # курс запечён — пересчитываем только сумму в рублях
            tx.amount_rub = tx.amount * tx.exchange_rate

        return tx

    async def delete_transaction(
        self, tx_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        tx = await self.get_transaction(tx_id, user_id)
        if tx.transfer_id is not None:
            raise ValidationFailedError(
                "Удаляйте перевод целиком через домен переводов."
            )
        await self._repo.delete(tx)

    async def _validate_category(
        self,
        user_id: uuid.UUID,
        category_id: uuid.UUID | None,
        kind: TransactionKind,
    ) -> None:
        if category_id is None:
            return
        category = await self._categories.get(category_id, user_id)
        if category is None:
            raise NotFoundError("Категория не найдена.")
        if category.is_archived:
            raise ValidationFailedError("Категория в архиве.")
        expected = _KIND_TO_CATEGORY.get(kind)
        if expected is not None and category.kind != expected:
            raise ValidationFailedError(
                "Тип категории не совпадает с типом операции (расход/доход)."
            )
