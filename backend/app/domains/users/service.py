"""Бизнес-логика домена users.

Профиль текущего юзера (безопасные поля: имя, часовой пояс, валюта
по умолчанию, локаль — без email/пароля) и набор активных валют.
Удаление аккаунта — мягкое (``is_active=False``); запрет для режима
single_user проверяется в роуте.
"""

import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.auth.models import User
from app.domains.currencies.models import UserCurrency
from app.domains.users.repository import UserRepository
from app.domains.users.schemas import (
    UserCurrenciesUpdate,
    UserUpdate,
)

__all__ = ["UserService"]


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._repo.get_user(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден.")
        return user

    async def update_profile(
        self, user_id: uuid.UUID, data: UserUpdate
    ) -> User:
        user = await self.get_user(user_id)
        fields = data.model_dump(exclude_unset=True)

        timezone = fields.get("timezone")
        if timezone is not None:
            _validate_timezone(timezone)

        currency = fields.get("default_currency")
        if currency is not None:
            code = currency.upper()
            if not await self._repo.currency_exists(code):
                raise ValidationFailedError(
                    f"Валюта {code} не найдена в справочнике."
                )
            fields["default_currency"] = code

        for key, value in fields.items():
            setattr(user, key, value)
        return user

    async def deactivate(self, user_id: uuid.UUID) -> None:
        user = await self.get_user(user_id)
        user.is_active = False

    async def list_currencies(self, user_id: uuid.UUID) -> list[UserCurrency]:
        return await self._repo.list_user_currencies(user_id)

    async def set_currencies(
        self, user_id: uuid.UUID, data: UserCurrenciesUpdate
    ) -> list[UserCurrency]:
        defaults = sum(1 for item in data.items if item.is_default)
        if defaults > 1:
            raise ValidationFailedError(
                "Валютой по умолчанию можно отметить только одну."
            )

        rows: list[UserCurrency] = []
        for item in data.items:
            code = item.currency_code.upper()
            if not await self._repo.currency_exists(code):
                raise ValidationFailedError(
                    f"Валюта {code} не найдена в справочнике."
                )
            rows.append(
                UserCurrency(
                    user_id=user_id,
                    currency_code=code,
                    is_default=item.is_default,
                    sort_order=item.sort_order,
                )
            )
        return await self._repo.replace_user_currencies(user_id, rows)


def _validate_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailedError(
            f"Неизвестный часовой пояс: {name}."
        ) from exc
