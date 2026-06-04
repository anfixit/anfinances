"""Юнит-тесты AccountService на фейковом репозитории."""

import uuid
from decimal import Decimal

import pytest

from app.core.enums import AccountType
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.models import Account
from app.domains.accounts.schemas import (
    AccountCreate,
    AccountUpdate,
)
from app.domains.accounts.service import AccountService

USER = uuid.uuid4()


class FakeRepo:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Account] = {}
        self.currencies = {"RUB", "USD"}

    async def list_active(self, user_id):
        return [
            a
            for a in self.items.values()
            if a.user_id == user_id and not a.is_archived
        ]

    async def get(self, account_id, user_id):
        a = self.items.get(account_id)
        if a is None or a.user_id != user_id:
            return None
        return a

    async def get_active_by_name(self, user_id, name):
        for a in self.items.values():
            if a.user_id == user_id and a.name == name and not a.is_archived:
                return a
        return None

    async def currency_exists(self, code):
        return code in self.currencies

    async def add(self, account):
        if account.id is None:
            account.id = uuid.uuid4()
        if account.is_archived is None:
            account.is_archived = False
        self.items[account.id] = account
        return account


def _create(name="Карта", code="RUB") -> AccountCreate:
    return AccountCreate(
        name=name,
        type=AccountType.CARD,
        currency_code=code,
        initial_balance=Decimal("100"),
    )


@pytest.fixture
def service() -> AccountService:
    return AccountService(FakeRepo())


async def test_create_ok(service: AccountService) -> None:
    acc = await service.create_account(USER, _create())
    assert acc.name == "Карта"
    assert acc.currency_code == "RUB"


async def test_create_unknown_currency(
    service: AccountService,
) -> None:
    with pytest.raises(ValidationFailedError):
        await service.create_account(USER, _create(code="XXX"))


async def test_create_duplicate_name(
    service: AccountService,
) -> None:
    await service.create_account(USER, _create())
    with pytest.raises(AlreadyExistsError):
        await service.create_account(USER, _create())


async def test_get_missing(service: AccountService) -> None:
    with pytest.raises(NotFoundError):
        await service.get_account(uuid.uuid4(), USER)


async def test_update_rename_conflict(
    service: AccountService,
) -> None:
    await service.create_account(USER, _create(name="A"))
    b = await service.create_account(USER, _create(name="B"))
    with pytest.raises(AlreadyExistsError):
        await service.update_account(b.id, USER, AccountUpdate(name="A"))


async def test_archive_then_reuse_name(
    service: AccountService,
) -> None:
    a = await service.create_account(USER, _create(name="A"))
    await service.archive_account(a.id, USER)
    # имя освободилось — можно создать заново
    b = await service.create_account(USER, _create(name="A"))
    assert b.id != a.id


async def test_restore_conflict(service: AccountService) -> None:
    a = await service.create_account(USER, _create(name="A"))
    await service.archive_account(a.id, USER)
    await service.create_account(USER, _create(name="A"))
    with pytest.raises(AlreadyExistsError):
        await service.restore_account(a.id, USER)
