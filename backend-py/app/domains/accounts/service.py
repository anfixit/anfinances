"""Бизнес-логика счетов: CRUD с soft-delete.

Все операции скоупятся по user_id. При создании и переименовании
проверяется существование валюты и уникальность имени среди
активных счетов — чтобы вернуть понятную ошибку вместо
нарушения внешнего ключа или unique-индекса.
"""

import uuid

from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.models import Account
from app.domains.accounts.repository import AccountRepository
from app.domains.accounts.schemas import (
    AccountCreate,
    AccountUpdate,
)

__all__ = ["AccountService"]


class AccountService:
    def __init__(self, repo: AccountRepository) -> None:
        self._repo = repo

    async def list_accounts(self, user_id: uuid.UUID) -> list[Account]:
        return await self._repo.list_active(user_id)

    async def get_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Account:
        account = await self._repo.get(account_id, user_id)
        if account is None:
            raise NotFoundError("Счёт не найден.")
        return account

    async def create_account(
        self, user_id: uuid.UUID, data: AccountCreate
    ) -> Account:
        code = data.currency_code.upper()
        if not await self._repo.currency_exists(code):
            raise ValidationFailedError(
                f"Валюта {code} не найдена в справочнике. "
                f"Создать счёт в несуществующей валюте нельзя: "
                f"иначе записи о деньгах нельзя будет корректно "
                f"пересчитать в рубли.",
                details=[{"field": "currency_code", "message": "Нет валюты."}],
            )

        if await self._repo.get_active_by_name(user_id, data.name):
            raise AlreadyExistsError(f"Счёт с именем «{data.name}» уже есть.")

        account = Account(
            user_id=user_id,
            name=data.name,
            type=data.type,
            currency_code=code,
            initial_balance=data.initial_balance,
            credit_limit=data.credit_limit,
            color=data.color,
            sort_order=data.sort_order,
            comments=data.comments,
        )
        return await self._repo.add(account)

    async def update_account(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        data: AccountUpdate,
    ) -> Account:
        account = await self.get_account(account_id, user_id)
        fields = data.model_dump(exclude_unset=True)

        new_name = fields.get("name")
        if new_name is not None and new_name != account.name:
            clash = await self._repo.get_active_by_name(user_id, new_name)
            if clash is not None and clash.id != account.id:
                raise AlreadyExistsError(
                    f"Счёт с именем «{new_name}» уже есть."
                )

        for key, value in fields.items():
            setattr(account, key, value)
        return account

    async def archive_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        account = await self.get_account(account_id, user_id)
        account.is_archived = True

    async def restore_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Account:
        account = await self.get_account(account_id, user_id)
        if not account.is_archived:
            return account
        clash = await self._repo.get_active_by_name(user_id, account.name)
        if clash is not None:
            raise AlreadyExistsError(
                f"Нельзя восстановить: активный счёт с именем "
                f"«{account.name}» уже существует."
            )
        account.is_archived = False
        return account
