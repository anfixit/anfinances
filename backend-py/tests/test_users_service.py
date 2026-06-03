"""Юнит-тесты UserService на фейковом репозитории.

Покрывают обновление профиля (валидация валюты и часового пояса),
мягкое удаление и замену набора валют (проверка существования и
единственности дефолта).
"""

import uuid

import pytest

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.auth.models import User
from app.domains.currencies.models import UserCurrency
from app.domains.users.schemas import (
    UserCurrenciesUpdate,
    UserCurrencyItem,
    UserUpdate,
)
from app.domains.users.service import UserService

USER = uuid.uuid4()
KNOWN_CURRENCIES = {"RUB", "USD", "EUR", "UZS"}


class FakeUserRepo:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}
        self.currencies = set(KNOWN_CURRENCIES)
        self.user_currencies: list[UserCurrency] = []

    async def get_user(self, user_id):
        return self.users.get(user_id)

    async def currency_exists(self, code):
        return code in self.currencies

    async def list_user_currencies(self, user_id):
        return [c for c in self.user_currencies if c.user_id == user_id]

    async def replace_user_currencies(self, user_id, items):
        self.user_currencies = [
            c for c in self.user_currencies if c.user_id != user_id
        ]
        for item in items:
            if item.id is None:
                item.id = uuid.uuid4()
            self.user_currencies.append(item)
        return items


def _user() -> User:
    user = User(
        email="a@b.com",
        hashed_password="x",
        name="Аня",
        timezone="Europe/Moscow",
        default_currency="RUB",
        locale="ru",
        is_active=True,
        is_verified=False,
    )
    user.id = USER
    return user


def _service() -> tuple[UserService, FakeUserRepo]:
    repo = FakeUserRepo()
    repo.users[USER] = _user()
    return UserService(repo), repo


async def test_update_profile_fields() -> None:
    svc, _ = _service()
    user = await svc.update_profile(
        USER,
        UserUpdate(
            name="Анфиса",
            timezone="Asia/Tashkent",
            default_currency="usd",
            locale="en",
        ),
    )
    assert user.name == "Анфиса"
    assert user.timezone == "Asia/Tashkent"
    assert user.default_currency == "USD"  # нормализовано к верхнему
    assert user.locale == "en"


async def test_update_unknown_currency_rejected() -> None:
    svc, _ = _service()
    with pytest.raises(ValidationFailedError):
        await svc.update_profile(USER, UserUpdate(default_currency="GBP"))


async def test_update_unknown_timezone_rejected() -> None:
    svc, _ = _service()
    with pytest.raises(ValidationFailedError):
        await svc.update_profile(USER, UserUpdate(timezone="Mars/Phobos"))


async def test_update_partial_keeps_other_fields() -> None:
    svc, _ = _service()
    user = await svc.update_profile(USER, UserUpdate(name="X"))
    assert user.name == "X"
    assert user.timezone == "Europe/Moscow"  # не тронут


async def test_update_missing_user() -> None:
    svc = UserService(FakeUserRepo())
    with pytest.raises(NotFoundError):
        await svc.update_profile(uuid.uuid4(), UserUpdate(name="X"))


async def test_deactivate() -> None:
    svc, repo = _service()
    await svc.deactivate(USER)
    assert repo.users[USER].is_active is False


async def test_set_currencies_replaces() -> None:
    svc, repo = _service()
    data = UserCurrenciesUpdate(
        items=[
            UserCurrencyItem(
                currency_code="rub", is_default=True, sort_order=0
            ),
            UserCurrencyItem(currency_code="USD", sort_order=1),
        ]
    )
    rows = await svc.set_currencies(USER, data)
    assert [r.currency_code for r in rows] == ["RUB", "USD"]
    assert rows[0].is_default is True
    assert len(repo.user_currencies) == 2


async def test_set_currencies_unknown_rejected() -> None:
    svc, _ = _service()
    data = UserCurrenciesUpdate(items=[UserCurrencyItem(currency_code="GBP")])
    with pytest.raises(ValidationFailedError):
        await svc.set_currencies(USER, data)


async def test_set_currencies_two_defaults_rejected() -> None:
    svc, _ = _service()
    data = UserCurrenciesUpdate(
        items=[
            UserCurrencyItem(currency_code="RUB", is_default=True),
            UserCurrencyItem(currency_code="USD", is_default=True),
        ]
    )
    with pytest.raises(ValidationFailedError):
        await svc.set_currencies(USER, data)


async def test_set_currencies_empty_clears() -> None:
    svc, repo = _service()
    repo.user_currencies.append(
        UserCurrency(user_id=USER, currency_code="RUB")
    )
    await svc.set_currencies(USER, UserCurrenciesUpdate(items=[]))
    assert repo.user_currencies == []


async def test_list_currencies() -> None:
    svc, repo = _service()
    uc = UserCurrency(
        user_id=USER, currency_code="RUB", is_default=True, sort_order=0
    )
    uc.id = uuid.uuid4()
    repo.user_currencies.append(uc)
    items = await svc.list_currencies(USER)
    assert len(items) == 1
    assert items[0].currency_code == "RUB"
