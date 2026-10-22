"""Бизнес-логика кредитов.

Кредит хранится отдельно от счёта. Платёж по кредиту создаёт
служебную TransactionKind.CREDIT_PAYMENT: она уменьшает баланс
счёта оплаты, но не считается обычным расходом. Расходной частью
кредитного платежа являются только проценты и комиссии.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from app.core.datetime import DEFAULT_TIMEZONE
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
from app.domains.credits.payoff import (
    PayoffDebt,
    PayoffStrategy,
    baseline_payoff,
    effective_since,
    simulate_payoff,
)
from app.domains.credits.projection import (
    CreditProjection,
    NeverAmortizesError,
    project_credit,
)
from app.domains.credits.repository import CreditRepository
from app.domains.credits.schemas import (
    CreditCreate,
    CreditPaymentCreate,
    CreditUpdate,
    PayoffBaselineRead,
    PayoffCreditRead,
    PayoffPlanRead,
    PayoffSkippedRead,
)
from app.domains.currencies.service import CurrencyService
from app.domains.transactions.models import Transaction
from app.domains.transactions.repository import TransactionRepository

__all__ = ["CreditService"]

_CENTS = Decimal("0.01")


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

    async def projection(
        self, credit_id: uuid.UUID, user_id: uuid.UUID
    ) -> CreditProjection:
        """Срок и разбивка ближайшего платежа по текущему остатку.

        Отсчёт процентов ведётся от даты последнего платежа, а если
        платежей ещё не было — от даты выдачи кредита.
        """
        credit = await self.get_credit(credit_id, user_id)
        if (
            credit.annual_rate is None
            or credit.monthly_payment is None
            or credit.payment_day is None
        ):
            raise ValidationFailedError(
                "Для расчёта графика нужны ставка, ежемесячный платёж "
                "и день платежа."
            )

        payments = await self._repo.list_payments(credit_id, user_id)
        if payments:
            since = max(p.date for p in payments).date()
        elif credit.start_date is not None:
            since = credit.start_date
        else:
            raise ValidationFailedError(
                "Нет ни одного платежа и не задана дата выдачи — "
                "не от чего считать проценты."
            )

        return project_credit(
            balance=credit.principal_balance,
            annual_rate=credit.annual_rate,
            monthly_payment=credit.monthly_payment,
            payment_day=credit.payment_day,
            since=since,
        )

    async def payoff_plan(
        self,
        user_id: uuid.UUID,
        strategy: PayoffStrategy,
        extra_monthly: Decimal,
        timezone_name: str = DEFAULT_TIMEZONE,
        now: datetime | None = None,
    ) -> PayoffPlanRead:
        """План погашения всех активных кредитов и выигрыш от него.

        Суммы сводятся в рубли по текущему курсу: доплата задаётся в
        рублях, а снежному кому нужно сравнивать остатки кредитов в
        разных валютах. Курс на годы вперёд никто не знает — для
        валютного кредита это оценка, для рублёвого — точный расчёт.

        Кредит, который посчитать нельзя, не роняет план и не
        зацикливает его, а попадает в ``skipped`` с причиной: ассистент
        должен сказать владельцу, что именно поправить.
        """
        if self._currencies is None:
            raise RuntimeError("CurrencyService is required for payoff.")
        currencies = self._currencies
        moment = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone_name))
        today = moment.date()
        last_paid = await self._repo.last_payment_dates(user_id)

        debts: list[PayoffDebt] = []
        currency_of: dict[uuid.UUID, str] = {}
        skipped: list[PayoffSkippedRead] = []
        for credit in await self._repo.list_active(user_id):
            if credit.principal_balance <= 0:
                continue
            # Отсчёт процентов — как у графика одного кредита: от
            # последнего платежа, а без платежей — от даты выдачи.
            paid_at = last_paid.get(credit.id)
            since = (
                paid_at.date() if paid_at is not None else credit.start_date
            )
            if (
                credit.annual_rate is None
                or credit.monthly_payment is None
                or credit.payment_day is None
                or since is None
            ):
                skipped.append(
                    PayoffSkippedRead(
                        credit_id=credit.id,
                        name=credit.name,
                        reason="missing_terms",
                        message=(
                            "Для плана нужны ставка, ежемесячный платёж, "
                            "день платежа и дата выдачи или хотя бы один "
                            "платёж."
                        ),
                    )
                )
                continue
            try:
                rate = await currencies.rate_to_rub(credit.currency_code)
            except NotFoundError as exc:
                skipped.append(
                    PayoffSkippedRead(
                        credit_id=credit.id,
                        name=credit.name,
                        reason="missing_rate",
                        message=exc.message,
                    )
                )
                continue

            debt = PayoffDebt(
                key=credit.id,
                name=credit.name,
                balance=_to_rub(credit.principal_balance, rate),
                annual_rate=credit.annual_rate,
                monthly_payment=_to_rub(credit.monthly_payment, rate),
                payment_day=credit.payment_day,
                since=effective_since(since, credit.payment_day, today),
            )
            # Не гасящийся кредит исключаем из обоих расчётов: иначе
            # и план, и база были бы бесконечными, а сравнение —
            # бессмысленным.
            try:
                baseline_payoff([debt], today)
            except NeverAmortizesError as exc:
                skipped.append(
                    PayoffSkippedRead(
                        credit_id=credit.id,
                        name=credit.name,
                        reason="never_amortizes",
                        message=str(exc),
                    )
                )
                continue
            debts.append(debt)
            currency_of[credit.id] = credit.currency_code

        plan = simulate_payoff(debts, strategy, extra_monthly, today)
        baseline = baseline_payoff(debts, today)
        return PayoffPlanRead(
            strategy=strategy,
            extra_monthly=extra_monthly,
            months_to_debt_free=plan.months_to_debt_free,
            debt_free_date=plan.debt_free_date,
            total_interest=plan.total_interest,
            order=[
                PayoffCreditRead(
                    credit_id=item.key,
                    name=item.name,
                    currency_code=currency_of[item.key],
                    payoff_date=item.payoff_date,
                    interest_paid=item.interest_paid,
                )
                for item in plan.debts
            ],
            baseline=PayoffBaselineRead(
                months_to_debt_free=baseline.months_to_debt_free,
                debt_free_date=baseline.debt_free_date,
                total_interest=baseline.total_interest,
            ),
            interest_saved=baseline.total_interest - plan.total_interest,
            months_saved=(
                baseline.months_to_debt_free - plan.months_to_debt_free
            ),
            skipped=skipped,
        )

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
            monthly_payment=data.monthly_payment,
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

    async def delete_payment(
        self, payment_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Удалить платёж и вернуть погашенное тело кредита.

        Платёж живёт в двух местах: строкой в кредите и списанием по
        счёту. Снести надо обе, иначе останется операция без платежа
        или платёж без списания. И обязательно вернуть
        ``principal_balance``: иначе строка исчезнет, а погашение
        останется засчитанным, и долг разойдётся с банком.
        """
        payment = await self._repo.get_payment(payment_id, user_id)
        if payment is None:
            raise NotFoundError("Платёж не найден.")

        credit = await self.get_credit(payment.credit_id, user_id)
        credit.principal_balance += payment.principal_amount

        if payment.transaction_id is not None:
            await self._repo.delete_transaction(payment.transaction_id)
        await self._repo.delete_payment(payment)

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


def _to_rub(amount: Decimal, rate: Decimal) -> Decimal:
    """Сумма в рублях; рублёвую не трогаем, чтобы не терять копейки.

    Для рублёвого кредита план обязан совпасть с его графиком до
    копейки, поэтому курс 1 не повод округлять остаток.
    """
    if rate == 1:
        return amount
    return (amount * rate).quantize(_CENTS, ROUND_HALF_UP)
