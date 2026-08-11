"""Полная проверка набора валют пользователя (AF-017).

Набор задаётся целиком, одним запросом. Раньше проверялось только
«не больше одного умолчания», и в базу проходили наборы без
умолчания вовсе, с повторяющимися кодами и с одинаковым порядком
сортировки — то есть с неопределённым порядком вывода.
"""

import uuid
from typing import Any, cast

import pytest

from app.core.exceptions import ValidationFailedError
from app.domains.users.schemas import (
    UserCurrenciesUpdate,
    UserCurrencyItem,
)
from app.domains.users.service import UserService

USER = uuid.uuid4()


class _Repo:
    def __init__(self, known: set[str]) -> None:
        self._known = known
        self.saved: list[Any] = []

    async def currency_exists(self, code: str) -> bool:
        return code in self._known

    async def replace_user_currencies(
        self, user_id: uuid.UUID, rows: list[Any]
    ) -> list[Any]:
        self.saved = rows
        return rows


def _service(known: set[str] | None = None) -> UserService:
    return UserService(cast(Any, _Repo(known or {"RUB", "USD", "UZS"})))


def _items(*rows: tuple[str, bool, int]) -> UserCurrenciesUpdate:
    return UserCurrenciesUpdate(
        items=[
            UserCurrencyItem(
                currency_code=code, is_default=default, sort_order=order
            )
            for code, default, order in rows
        ]
    )


async def test_valid_set_passes() -> None:
    service = _service()
    await service.set_currencies(
        USER, _items(("RUB", True, 0), ("USD", False, 1))
    )


async def test_two_defaults_rejected() -> None:
    service = _service()
    with pytest.raises(ValidationFailedError):
        await service.set_currencies(
            USER, _items(("RUB", True, 0), ("USD", True, 1))
        )


async def test_no_default_rejected() -> None:
    """Без основной валюты не в чем показывать итоги."""
    service = _service()
    with pytest.raises(ValidationFailedError):
        await service.set_currencies(
            USER, _items(("RUB", False, 0), ("USD", False, 1))
        )


async def test_duplicate_codes_rejected() -> None:
    service = _service()
    with pytest.raises(ValidationFailedError):
        await service.set_currencies(
            USER, _items(("RUB", True, 0), ("RUB", False, 1))
        )


async def test_duplicate_sort_order_rejected() -> None:
    """Одинаковый порядок — это неопределённый порядок вывода."""
    service = _service()
    with pytest.raises(ValidationFailedError):
        await service.set_currencies(
            USER, _items(("RUB", True, 0), ("USD", False, 0))
        )


async def test_unknown_currency_rejected() -> None:
    service = _service()
    with pytest.raises(ValidationFailedError):
        await service.set_currencies(USER, _items(("XXX", True, 0)))


async def test_empty_set_is_allowed() -> None:
    """Пустой набор — способ очистить список, а не поломка."""
    service = _service()
    await service.set_currencies(USER, UserCurrenciesUpdate(items=[]))
