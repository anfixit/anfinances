"""Бизнес-логика переводов между счетами.

Перевод — это пара транзакций (kind=transfer) с общим
transfer_id: списание с источника и зачисление на получатель.
Сумму зачисления вводит пользователь (фактический курс банка),
поэтому рублёвый эквивалент получателя приравнивается к рублёвому
эквиваленту источника — перевод не создаёт прибыли/убытка, баланс
не плывёт. Фактический курс получателя запекается как
amount_rub / amount_to.

Комиссия (если задана) — отдельная строка kind=expense в валюте
счёта-источника, с тем же transfer_id и выбранной пользователем
expense-категорией.
"""

import uuid
from decimal import Decimal

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import (
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.repository import AccountRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.models import Transaction, Transfer
from app.domains.transactions.repository import (
    TransactionRepository,
)
from app.domains.transactions.schemas import TransferCreate

__all__ = ["TransferService"]


class TransferService:
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

    async def create_transfer(
        self, user_id: uuid.UUID, data: TransferCreate
    ) -> tuple[Transfer, list[Transaction]]:
        src = await self._accounts.get(data.from_account_id, user_id)
        if src is None:
            raise NotFoundError("Счёт-источник не найден.")
        dst = await self._accounts.get(data.to_account_id, user_id)
        if dst is None:
            raise NotFoundError("Счёт-получатель не найден.")

        await self._validate_fee_category(
            user_id, data.fee_category_id, data.fee_amount
        )

        transfer = await self._repo.add_transfer(Transfer(user_id=user_id))
        created: list[Transaction] = []

        # Нога-источник: рубли по официальному курсу валюты источника.
        src_rate = await self._currencies.rate_to_rub(src.currency_code)
        src_rub = data.amount_from * src_rate
        created.append(
            await self._repo.add(
                Transaction(
                    user_id=user_id,
                    transfer_id=transfer.id,
                    account_id=src.id,
                    kind=TransactionKind.TRANSFER,
                    amount=data.amount_from,
                    currency_code=src.currency_code,
                    amount_rub=src_rub,
                    exchange_rate=src_rate,
                    category_id=None,
                    date=data.date,
                    comment=data.comment,
                )
            )
        )

        # Нога-получатель: рублёвый эквивалент = источнику (баланс
        # не плывёт), фактический курс = src_rub / amount_to.
        dst_rate = src_rub / data.amount_to
        created.append(
            await self._repo.add(
                Transaction(
                    user_id=user_id,
                    transfer_id=transfer.id,
                    account_id=dst.id,
                    kind=TransactionKind.TRANSFER,
                    amount=data.amount_to,
                    currency_code=dst.currency_code,
                    amount_rub=src_rub,
                    exchange_rate=dst_rate,
                    category_id=None,
                    date=data.date,
                    comment=data.comment,
                )
            )
        )

        # Комиссия — расход в валюте источника, с transfer_id.
        if data.fee_amount is not None:
            fee_rub = data.fee_amount * src_rate
            created.append(
                await self._repo.add(
                    Transaction(
                        user_id=user_id,
                        transfer_id=transfer.id,
                        account_id=src.id,
                        kind=TransactionKind.EXPENSE,
                        amount=data.fee_amount,
                        currency_code=src.currency_code,
                        amount_rub=fee_rub,
                        exchange_rate=src_rate,
                        category_id=data.fee_category_id,
                        date=data.date,
                        comment="Комиссия за перевод",
                    )
                )
            )

        return transfer, created

    async def get_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Transfer, list[Transaction]]:
        transfer = await self._repo.get_transfer(transfer_id, user_id)
        if transfer is None:
            raise NotFoundError("Перевод не найден.")
        legs = await self._repo.list_transfer_legs(transfer_id)
        return transfer, legs

    async def delete_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        transfer = await self._repo.get_transfer(transfer_id, user_id)
        if transfer is None:
            raise NotFoundError("Перевод не найден.")
        legs = await self._repo.list_transfer_legs(transfer_id)
        for leg in legs:
            await self._repo.delete(leg)

    async def _validate_fee_category(
        self,
        user_id: uuid.UUID,
        fee_category_id: uuid.UUID | None,
        fee_amount: Decimal | None,
    ) -> None:
        if fee_category_id is None:
            return
        if fee_amount is None:
            raise ValidationFailedError(
                "Категория комиссии задана без суммы комиссии."
            )
        category = await self._categories.get(fee_category_id, user_id)
        if category is None:
            raise NotFoundError("Категория комиссии не найдена.")
        if category.is_archived:
            raise ValidationFailedError("Категория комиссии в архиве.")
        if category.kind != CategoryKind.EXPENSE:
            raise ValidationFailedError(
                "Категория комиссии должна быть расходной."
            )
