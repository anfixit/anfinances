"""Архивация счёта с ненулевым остатком требует подтверждения.

Архивный счёт исчезает из капитала. Если на нём остались деньги или
долг, итог молча меняется на эту сумму, а заметно это станет через
неделю — когда уже не вспомнить, что именно архивировали.
"""

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest

from app.core.exceptions import ValidationFailedError
from app.domains.accounts.service import AccountService


class _Account:
    def __init__(self, initial: Decimal) -> None:
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.name = "Альфа"
        self.currency_code = "RUB"
        self.initial_balance = initial
        self.is_archived = False


class _Repo:
    def __init__(self, account: _Account, moved: Decimal) -> None:
        self._account = account
        self._moved = moved

    async def get(self, account_id: uuid.UUID, user_id: uuid.UUID) -> _Account:
        return self._account

    async def transaction_total(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> Decimal:
        return self._moved


def _service(
    initial: Decimal, moved: Decimal = Decimal(0)
) -> tuple[AccountService, _Account]:
    account = _Account(initial)
    return AccountService(cast(Any, _Repo(account, moved))), account


async def test_empty_account_archives_without_questions() -> None:
    service, account = _service(Decimal("0"))
    await service.archive_account(account.id, account.user_id)
    assert account.is_archived is True


async def test_account_with_money_is_not_archived_silently() -> None:
    service, account = _service(Decimal("5000"))
    with pytest.raises(ValidationFailedError) as caught:
        await service.archive_account(account.id, account.user_id)
    assert "5000" in str(caught.value)
    assert account.is_archived is False


async def test_account_with_debt_is_not_archived_silently() -> None:
    """Долг теряется из капитала так же незаметно, как деньги."""
    service, account = _service(Decimal("-280650.24"))
    with pytest.raises(ValidationFailedError):
        await service.archive_account(account.id, account.user_id)
    assert account.is_archived is False


async def test_balance_counts_transactions_not_only_initial() -> None:
    service, account = _service(Decimal("1000"), moved=Decimal("-1000"))
    await service.archive_account(account.id, account.user_id)
    assert account.is_archived is True


async def test_force_archives_anyway() -> None:
    """Подтвердила осознанно — архивируем и не спорим."""
    service, account = _service(Decimal("5000"))
    await service.archive_account(account.id, account.user_id, force=True)
    assert account.is_archived is True
