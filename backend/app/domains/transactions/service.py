"""Бизнес-логика домена transactions.

Соглашение знаков (Стратегия А): знак amount и amount_rub
отражает направление движения денег по счёту.
- доход / входящая нога перевода:  amount > 0
- расход / исходящая нога / комиссия: amount < 0
Тогда баланс счёта = initial_balance + Σ amount (одна сумма,
без разбора направлений). Пользователь и API всегда оперируют
положительной суммой — знак проставляет сервис по kind.

TransactionService — обычные операции (расход/доход): транзакция
в валюте своего счёта, курс к рублю запекается в exchange_rate,
amount_rub не плывёт при обновлении курсов.

TransferService — переводы: пара ног (kind=transfer) с общим
transfer_id. Рублёвый эквивалент получателя по модулю равен
источнику (баланс не плывёт), фактический курс банка запекается
как |amount_rub| / amount_to. Комиссия (если задана) — отдельная
строка kind=expense с тем же transfer_id, в валюте источника, с
категорией из запроса.

Удаление обычной транзакции физическое. Удаление перевода удаляет
все его ноги и сам узел Transfer.
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
    TransactionFilter,
    TransactionRepository,
)
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
    TransferCreate,
    TransferUpdate,
)

__all__ = ["TransactionService", "TransferService"]

_KIND_TO_CATEGORY = {
    TransactionKind.EXPENSE: CategoryKind.EXPENSE,
    TransactionKind.INCOME: CategoryKind.INCOME,
}


def _signed(amount: Decimal, kind: TransactionKind) -> Decimal:
    """Применить знак к положительной сумме по типу операции.

    Доход — плюс, расход — минус. Сумма на входе всегда > 0.
    """
    if kind in {TransactionKind.EXPENSE, TransactionKind.CREDIT_PAYMENT}:
        return -amount
    return amount


async def _category_snapshot(
    categories: CategoryRepository,
    user_id: uuid.UUID,
    category_id: uuid.UUID | None,
    expected: CategoryKind,
    *,
    not_found: str,
    archived: str,
    kind_mismatch: str,
) -> tuple[str | None, str | None]:
    if category_id is None:
        return None, None

    category = await categories.get(category_id, user_id)
    if category is None:
        raise NotFoundError(not_found)
    if category.is_archived:
        raise ValidationFailedError(archived)
    if category.kind != expected:
        raise ValidationFailedError(kind_mismatch)

    if category.parent_id is None:
        return category.name, None

    parent = await categories.get(category.parent_id, user_id)
    if parent is None:
        return category.name, None
    return parent.name, category.name


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

        (
            category_name_snapshot,
            subcategory_name_snapshot,
        ) = await self._validate_category(user_id, data.category_id, data.kind)

        rate = await self._currencies.rate_to_rub(account.currency_code)
        amount = _signed(data.amount, data.kind)
        amount_rub = amount * rate

        tx = Transaction(
            user_id=user_id,
            account_id=account.id,
            kind=data.kind,
            amount=amount,
            currency_code=account.currency_code,
            amount_rub=amount_rub,
            exchange_rate=rate,
            category_id=data.category_id,
            category_name_snapshot=category_name_snapshot,
            subcategory_name_snapshot=subcategory_name_snapshot,
            account_name_snapshot=account.name,
            to_account_name_snapshot=None,
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
        if tx.kind == TransactionKind.CREDIT_PAYMENT:
            raise ValidationFailedError(
                "Кредитный платёж редактируется в домене кредитов."
            )

        fields = data.model_dump(exclude_unset=True)

        if "category_id" in fields:
            (
                category_name_snapshot,
                subcategory_name_snapshot,
            ) = await self._validate_category(
                user_id, fields["category_id"], tx.kind
            )

        for key, value in fields.items():
            if key == "amount":
                continue
            setattr(tx, key, value)

        if "category_id" in fields:
            tx.category_name_snapshot = category_name_snapshot
            tx.subcategory_name_snapshot = subcategory_name_snapshot

        if "amount" in fields:
            # на входе положительная сумма — заново проставляем
            # знак по kind; курс запечён, меняется только модуль
            tx.amount = _signed(fields["amount"], tx.kind)
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
        if tx.kind == TransactionKind.CREDIT_PAYMENT:
            raise ValidationFailedError(
                "Кредитный платёж удаляется в домене кредитов."
            )
        await self._repo.delete(tx)

    async def _validate_category(
        self,
        user_id: uuid.UUID,
        category_id: uuid.UUID | None,
        kind: TransactionKind,
    ) -> tuple[str | None, str | None]:
        expected = _KIND_TO_CATEGORY.get(kind)
        if expected is None:
            return None, None

        return await _category_snapshot(
            self._categories,
            user_id,
            category_id,
            expected,
            not_found="Категория не найдена.",
            archived="Категория в архиве.",
            kind_mismatch=(
                "Тип категории не совпадает с типом операции (расход/доход)."
            ),
        )


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

        (
            fee_category_name_snapshot,
            fee_subcategory_name_snapshot,
        ) = await self._validate_fee_category(
            user_id, data.fee_category_id, data.fee_amount
        )

        transfer = await self._repo.add_transfer(Transfer(user_id=user_id))
        created: list[Transaction] = []

        # Нога-источник: деньги уходят — суммы отрицательные.
        src_rate = await self._currencies.rate_to_rub(src.currency_code)
        src_rub = data.amount_from * src_rate
        created.append(
            await self._repo.add(
                Transaction(
                    user_id=user_id,
                    transfer_id=transfer.id,
                    account_id=src.id,
                    kind=TransactionKind.TRANSFER,
                    amount=-data.amount_from,
                    currency_code=src.currency_code,
                    amount_rub=-src_rub,
                    exchange_rate=src_rate,
                    category_id=None,
                    category_name_snapshot=None,
                    subcategory_name_snapshot=None,
                    account_name_snapshot=src.name,
                    to_account_name_snapshot=dst.name,
                    date=data.date,
                    comment=data.comment,
                )
            )
        )

        # Нога-получатель: деньги приходят — суммы положительные.
        # Рублёвый эквивалент по модулю = источнику (баланс не
        # плывёт), фактический курс = src_rub / amount_to.
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
                    category_name_snapshot=None,
                    subcategory_name_snapshot=None,
                    account_name_snapshot=dst.name,
                    to_account_name_snapshot=src.name,
                    date=data.date,
                    comment=data.comment,
                )
            )
        )

        # Комиссия — расход в валюте источника, суммы отрицательные.
        if data.fee_amount is not None:
            fee_rub = data.fee_amount * src_rate
            created.append(
                await self._repo.add(
                    Transaction(
                        user_id=user_id,
                        transfer_id=transfer.id,
                        account_id=src.id,
                        kind=TransactionKind.EXPENSE,
                        amount=-data.fee_amount,
                        currency_code=src.currency_code,
                        amount_rub=-fee_rub,
                        exchange_rate=src_rate,
                        category_id=data.fee_category_id,
                        category_name_snapshot=fee_category_name_snapshot,
                        subcategory_name_snapshot=(
                            fee_subcategory_name_snapshot
                        ),
                        account_name_snapshot=src.name,
                        to_account_name_snapshot=None,
                        date=data.date,
                        comment="Комиссия за перевод",
                    )
                )
            )

        return transfer, created

    async def update_transfer(
        self,
        transfer_id: uuid.UUID,
        user_id: uuid.UUID,
        data: TransferUpdate,
    ) -> tuple[Transfer, list[Transaction]]:
        transfer, legs = await self.get_transfer(transfer_id, user_id)
        src_leg, dst_leg, fee_leg = self._split_legs(legs)

        src = await self._accounts.get(data.from_account_id, user_id)
        if src is None:
            raise NotFoundError("Счёт-источник не найден.")
        dst = await self._accounts.get(data.to_account_id, user_id)
        if dst is None:
            raise NotFoundError("Счёт-получатель не найден.")

        (
            fee_category_name_snapshot,
            fee_subcategory_name_snapshot,
        ) = await self._validate_fee_category(
            user_id, data.fee_category_id, data.fee_amount
        )

        src_rate = await self._currencies.rate_to_rub(src.currency_code)
        src_rub = data.amount_from * src_rate
        dst_rate = src_rub / data.amount_to

        src_leg.account_id = src.id
        src_leg.account_name_snapshot = src.name
        src_leg.to_account_name_snapshot = dst.name
        src_leg.category_name_snapshot = None
        src_leg.subcategory_name_snapshot = None
        src_leg.amount = -data.amount_from
        src_leg.currency_code = src.currency_code
        src_leg.amount_rub = -src_rub
        src_leg.exchange_rate = src_rate
        src_leg.date = data.date
        src_leg.comment = data.comment

        dst_leg.account_id = dst.id
        dst_leg.account_name_snapshot = dst.name
        dst_leg.to_account_name_snapshot = src.name
        dst_leg.category_name_snapshot = None
        dst_leg.subcategory_name_snapshot = None
        dst_leg.amount = data.amount_to
        dst_leg.currency_code = dst.currency_code
        dst_leg.amount_rub = src_rub
        dst_leg.exchange_rate = dst_rate
        dst_leg.date = data.date
        dst_leg.comment = data.comment

        if data.fee_amount is None:
            if fee_leg is not None:
                await self._repo.delete(fee_leg)
            return transfer, [src_leg, dst_leg]

        fee_rub = data.fee_amount * src_rate
        if fee_leg is None:
            fee_leg = await self._repo.add(
                Transaction(
                    user_id=user_id,
                    transfer_id=transfer.id,
                    account_id=src.id,
                    kind=TransactionKind.EXPENSE,
                    amount=-data.fee_amount,
                    currency_code=src.currency_code,
                    amount_rub=-fee_rub,
                    exchange_rate=src_rate,
                    category_id=data.fee_category_id,
                    category_name_snapshot=fee_category_name_snapshot,
                    subcategory_name_snapshot=fee_subcategory_name_snapshot,
                    account_name_snapshot=src.name,
                    to_account_name_snapshot=None,
                    date=data.date,
                    comment="Комиссия за перевод",
                )
            )
        else:
            fee_leg.account_id = src.id
            fee_leg.account_name_snapshot = src.name
            fee_leg.to_account_name_snapshot = None
            fee_leg.category_name_snapshot = fee_category_name_snapshot
            fee_leg.subcategory_name_snapshot = fee_subcategory_name_snapshot
            fee_leg.amount = -data.fee_amount
            fee_leg.currency_code = src.currency_code
            fee_leg.amount_rub = -fee_rub
            fee_leg.exchange_rate = src_rate
            fee_leg.category_id = data.fee_category_id
            fee_leg.date = data.date

        return transfer, [src_leg, dst_leg, fee_leg]

    @staticmethod
    def _split_legs(
        legs: list[Transaction],
    ) -> tuple[Transaction, Transaction, Transaction | None]:
        transfer_legs = [
            leg for leg in legs if leg.kind == TransactionKind.TRANSFER
        ]
        source = next(
            (leg for leg in transfer_legs if leg.amount < 0),
            None,
        )
        destination = next(
            (leg for leg in transfer_legs if leg.amount > 0),
            None,
        )
        fee = next(
            (leg for leg in legs if leg.kind == TransactionKind.EXPENSE),
            None,
        )
        if source is None or destination is None:
            raise ValidationFailedError(
                "Перевод повреждён: не найдены обе его части."
            )
        return source, destination, fee

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
        # Сначала ноги (у них FK на transfers.id), затем сам узел —
        # иначе остаётся «сирота» в таблице transfers.
        for leg in legs:
            await self._repo.delete(leg)
        await self._repo.delete_transfer(transfer)

    async def _validate_fee_category(
        self,
        user_id: uuid.UUID,
        fee_category_id: uuid.UUID | None,
        fee_amount: Decimal | None,
    ) -> tuple[str | None, str | None]:
        if fee_category_id is None:
            return None, None
        if fee_amount is None:
            raise ValidationFailedError(
                "Категория комиссии задана без суммы комиссии."
            )

        return await _category_snapshot(
            self._categories,
            user_id,
            fee_category_id,
            CategoryKind.EXPENSE,
            not_found="Категория комиссии не найдена.",
            archived="Категория комиссии в архиве.",
            kind_mismatch=(
                "Комиссия учитывается только по расходной категории."
            ),
        )
