"""Бизнес-логика кредитов.

На этом этапе домен хранит кредитные обязательства, но ещё не
создаёт платежи и не меняет transactions. Это защищает учёт от
ошибки, где весь кредитный платёж становится расходом.
"""

import uuid
from decimal import Decimal

from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.repository import AccountRepository
from app.domains.credits.models import Credit
from app.domains.credits.repository import CreditRepository
from app.domains.credits.schemas import CreditCreate, CreditUpdate

__all__ = ["CreditService"]


class CreditService:
    def __init__(
        self,
        repo: CreditRepository,
        accounts: AccountRepository,
    ) -> None:
        self._repo = repo
        self._accounts = accounts

    async def list_credits(self, user_id: uuid.UUID) -> list[Credit]:
        return await self._repo.list_active(user_id)

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
