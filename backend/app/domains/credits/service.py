"""Бизнес-логика кредитов.

Кредит хранится отдельно от счёта. Платёж по кредиту создаёт
служебную TransactionKind.CREDIT_PAYMENT: она уменьшает баланс
счёта оплаты, но не считается обычным расходом. Расходной частью
кредитного платежа являются только проценты и комиссии.
"""

import uuid
from decimal import Decimal

from app.core.enums import CategoryKind, TransactionKind
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.models import Account
from app.domains.accounts.repository import AccountRepository
from app.domains.categories.models import Category
from app.domains.categories.repository import CategoryRepository
from app.domains.credits.models import Credit, CreditPayment
from app.domains.credits.repository import CreditRepository
from app.domains.credits.schemas import (
    CreditCreate,
    CreditPaymentCreate,
    CreditUpdate,
)
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import TransactionRepository

__all__ = ["CreditService"]


class CreditService:
    def __init__(
        self,
        repo: CreditRepository,
        accounts: AccountRepository,
        categories: CategoryRepository | None = None,
        transactions: TransactionRepository | None = None,
        currencies: CurrencyService | None = None,
    ) -> None:
        self._repo = repo
        self._accounts = accounts
        self._categories = categories
        self._transactions = transactions
        self._currencies = currencies

    async def list_credits(self, user_id: uuid.UUID) -> list[Credit]:
        return await self._repo.list_active(user_id)

    async def list_payments(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[CreditPayment]:
        await self.get_credit(credit_id, user_id)
        return await self._repo.list_payments(credit_id, user_id)

    async def get_credit(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> Credit:
        credit = await self._repo.get(credit_id, user_id)
        if credit is None:
            raise NotFoundError("Кредит не найден.")
        return credit

    async def create_credit(
        self, user_id: uuid.UUID, data: CreditCreate
    ) -> Credit:
        code = data.currency_code.upper()
        await self._validate_currency(code)
        await self._validate_unique_name(user_id, data.name)
        await self._validate_linked_account(
            data.linked_account_id,
            user_id,
            code,
        )

        credit = Credit(
            user_id=user_id,
            name=data.name,
            lender=data.lender,
            currency_code=code,
            principal_initial=data.principal_initial,
            principal_balance=data.principal_initial,
            annual_rate=data.annual_rate,
            term_months=data.term_months,
            start_date=data.start_date,
            payment_day=data.payment_day,
            linked_account_id=data.linked_account_id,
            comments=data.comments,
        )
        return await self._repo.add(credit)

    async def update_credit(
        self,
        credit_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreditUpdate,
    ) -> Credit:
        credit = await self.get_credit(credit_id, user_id)
        fields = data.model_dump(exclude_unset=True)

        new_name = fields.get("name")
        if new_name is not None and new_name != credit.name:
            await self._validate_unique_name(user_id, new_name)

        principal_initial = fields.pop("principal_initial", None)
        if principal_initial is not None:
            await self._update_initial_principal(
                credit,
                user_id,
                principal_initial,
            )

        linked_account_id = fields.get("linked_account_id")
        if "linked_account_id" in fields:
            await self._validate_linked_account(
                linked_account_id,
                user_id,
                credit.currency_code,
            )

        for key, value in fields.items():
            setattr(credit, key, value)
        return credit

    async def create_payment(
        self,
        credit_id: uuid.UUID,
        user_id: uuid.UUID,
        data: CreditPaymentCreate,
    ) -> CreditPayment:
        categories, transactions, currencies = self._payment_dependencies()
        credit = await self.get_credit(credit_id, user_id)
        if credit.is_archived:
            raise ValidationFailedError("Архивный кредит нельзя погашать.")

        account = await self._validate_payment_account(
            data.payment_account_id,
            user_id,
            credit.currency_code,
        )
        await self._validate_payment_categories(categories, user_id, data)
        self._validate_principal_amount(credit, data.principal_amount)

        rate = await currencies.rate_to_rub(account.currency_code)
        signed_total = -data.total_amount
        tx = await transactions.add(
            Transaction(
                user_id=user_id,
                transfer_id=None,
                account_id=account.id,
                kind=TransactionKind.CREDIT_PAYMENT,
                amount=signed_total,
                currency_code=account.currency_code,
                amount_rub=signed_total * rate,
                exchange_rate=rate,
                category_id=None,
                category_name_snapshot=None,
                subcategory_name_snapshot=None,
                account_name_snapshot=account.name,
                to_account_name_snapshot=None,
                required=None,
                date=data.date,
                comment=data.comment or f"Платёж по кредиту: {credit.name}",
            )
        )

        payment = await self._repo.add_payment(
            CreditPayment(
                user_id=user_id,
                credit_id=credit.id,
                payment_account_id=account.id,
                transaction_id=tx.id,
                date=data.date,
                total_amount=data.total_amount,
                principal_amount=data.principal_amount,
                interest_amount=data.interest_amount,
                fee_amount=data.fee_amount,
                currency_code=credit.currency_code,
                interest_category_id=data.interest_category_id,
                fee_category_id=data.fee_category_id,
                comment=data.comment,
            )
        )
        credit.principal_balance -= data.principal_amount
        return payment

    async def archive_credit(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        credit = await self.get_credit(credit_id, user_id)
        credit.is_archived = True

    async def _validate_currency(self, code: str) -> None:
        if not await self._repo.currency_exists(code):
            raise ValidationFailedError(
                f"Валюта {code} не найдена в справочнике.",
                details=[{"field": "currency_code", "message": "Нет валюты."}],
            )

    async def _validate_unique_name(
        self, user_id: uuid.UUID, name: str
    ) -> None:
        if await self._repo.get_active_by_name(user_id, name):
            raise AlreadyExistsError(f'Кредит с именем "{name}" уже есть.')

    async def _validate_linked_account(
        self,
        account_id: uuid.UUID | None,
        user_id: uuid.UUID,
        currency_code: str,
    ) -> None:
        if account_id is None:
            return

        account = await self._accounts.get(account_id, user_id)
        if account is None:
            raise NotFoundError("Связанный счёт не найден.")
        if account.is_archived:
            raise ValidationFailedError("Связанный счёт в архиве.")
        if account.currency_code != currency_code:
            raise ValidationFailedError(
                "Валюта связанного счёта должна совпадать с валютой кредита.",
                details=[
                    {
                        "field": "linked_account_id",
                        "message": "Валюта счёта не совпадает.",
                    }
                ],
            )

    async def _validate_payment_account(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        currency_code: str,
    ) -> Account:
        account = await self._accounts.get(account_id, user_id)
        if account is None:
            raise NotFoundError("Счёт оплаты не найден.")
        if account.is_archived:
            raise ValidationFailedError("Счёт оплаты в архиве.")
        if account.currency_code != currency_code:
            raise ValidationFailedError(
                "Валюта счёта оплаты должна совпадать с валютой кредита.",
                details=[
                    {
                        "field": "payment_account_id",
                        "message": "Валюта счёта не совпадает.",
                    }
                ],
            )
        return account

    async def _validate_payment_categories(
        self,
        categories: CategoryRepository,
        user_id: uuid.UUID,
        data: CreditPaymentCreate,
    ) -> None:
        await self._validate_expense_category(
            categories,
            user_id,
            data.interest_category_id,
            data.interest_amount,
            field="interest_category_id",
        )
        await self._validate_expense_category(
            categories,
            user_id,
            data.fee_category_id,
            data.fee_amount,
            field="fee_category_id",
        )

    async def _validate_expense_category(
        self,
        categories: CategoryRepository,
        user_id: uuid.UUID,
        category_id: uuid.UUID | None,
        amount: Decimal,
        *,
        field: str,
    ) -> Category | None:
        if category_id is None:
            return None
        if amount == 0:
            raise ValidationFailedError(
                "Категория задана для нулевой части платежа.",
                details=[
                    {
                        "field": field,
                        "message": "Укажите сумму или уберите категорию.",
                    }
                ],
            )
        category = await categories.get(category_id, user_id)
        if category is None:
            raise NotFoundError("Категория платежа не найдена.")
        if category.is_archived:
            raise ValidationFailedError("Категория платежа в архиве.")
        if category.kind != CategoryKind.EXPENSE:
            raise ValidationFailedError(
                "Проценты и комиссии относятся только к расходам.",
                details=[
                    {
                        "field": field,
                        "message": "Нужна расходная категория.",
                    }
                ],
            )
        return category

    @staticmethod
    def _validate_principal_amount(
        credit: Credit,
        principal_amount: Decimal,
    ) -> None:
        if principal_amount > credit.principal_balance:
            raise ValidationFailedError(
                "Тело платежа не может превышать остаток долга.",
                details=[
                    {
                        "field": "principal_amount",
                        "message": "Сумма больше остатка долга.",
                    }
                ],
            )

    async def _update_initial_principal(
        self,
        credit: Credit,
        user_id: uuid.UUID,
        principal_initial: Decimal,
    ) -> None:
        if principal_initial == credit.principal_initial:
            return
        if await self._repo.has_payments(credit.id, user_id):
            raise ValidationFailedError(
                "Начальную сумму кредита нельзя менять после платежей.",
                details=[
                    {
                        "field": "principal_initial",
                        "message": (
                            "После первого платежа сумма заблокирована."
                        ),
                    }
                ],
            )
        credit.principal_initial = principal_initial
        credit.principal_balance = principal_initial

    def _payment_dependencies(
        self,
    ) -> tuple[CategoryRepository, TransactionRepository, CurrencyService]:
        if self._categories is None:
            raise RuntimeError("CategoryRepository is required for payments.")
        if self._transactions is None:
            raise RuntimeError(
                "TransactionRepository is required for payments."
            )
        if self._currencies is None:
            raise RuntimeError("CurrencyService is required for payments.")
        return self._categories, self._transactions, self._currencies
