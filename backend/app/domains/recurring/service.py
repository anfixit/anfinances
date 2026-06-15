"""Бизнес-логика домена recurring (план-минимум).

Регулярные обязательные траты по расходным категориям.
``amount_rub`` запекается при создании/обновлении из
``monthly_amount`` по текущему курсу (как в transactions);
при сильном движении курса обновляется пере-сохранением.
Удаление — архивирование (ADR-010).

``generate_from_categories`` предзаполняет план: берёт обязательные
расходы за последние ``_MONTHS_WINDOW`` полных месяцев, группирует
по категории и создаёт записи со средним месячным расходом в рублях
для тех расходных категорий, у которых ещё нет активной записи.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import CategoryKind, RequiredKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.categories.repository import CategoryRepository
from app.domains.currencies.service import CurrencyService
from app.domains.recurring.models import RecurringExpense
from app.domains.recurring.repository import RecurringRepository
from app.domains.recurring.schemas import (
    RecurringCreate,
    RecurringUpdate,
)

__all__ = ["RecurringService"]

_MONTHS_WINDOW = 3
_RUB = "RUB"
_CENTS = Decimal("0.01")


class RecurringService:
    def __init__(
        self,
        repo: RecurringRepository,
        categories: CategoryRepository,
        currencies: CurrencyService,
    ) -> None:
        self._repo = repo
        self._categories = categories
        self._currencies = currencies

    async def list_recurring(
        self, user_id: uuid.UUID
    ) -> list[RecurringExpense]:
        return await self._repo.list_active(user_id)

    async def get_recurring(
        self, recurring_id: uuid.UUID, user_id: uuid.UUID
    ) -> RecurringExpense:
        item = await self._repo.get(recurring_id, user_id)
        if item is None:
            raise NotFoundError("Регулярный платёж не найден.")
        return item

    async def create_recurring(
        self, user_id: uuid.UUID, data: RecurringCreate
    ) -> RecurringExpense:
        await self._validate_category(user_id, data.category_id)
        code = data.currency_code.upper()
        amount_rub = (
            await self._currencies.convert(data.monthly_amount, code, _RUB)
            if data.monthly_amount is not None
            else None
        )
        item = RecurringExpense(
            user_id=user_id,
            required=data.required,
            category_id=data.category_id,
            name=data.name,
            monthly_amount=data.monthly_amount,
            currency_code=code,
            amount_rub=amount_rub,
            comments=data.comments,
        )
        return await self._repo.add(item)

    async def update_recurring(
        self,
        recurring_id: uuid.UUID,
        user_id: uuid.UUID,
        data: RecurringUpdate,
    ) -> RecurringExpense:
        item = await self.get_recurring(recurring_id, user_id)
        fields = data.model_dump(exclude_unset=True)

        if "category_id" in fields:
            await self._validate_category(user_id, fields["category_id"])
        if "currency_code" in fields and fields["currency_code"] is not None:
            fields["currency_code"] = fields["currency_code"].upper()

        for key, value in fields.items():
            setattr(item, key, value)

        # Пересчёт рублёвого эквивалента, если изменилась сумма
        # или валюта.
        if "monthly_amount" in fields or "currency_code" in fields:
            item.amount_rub = (
                await self._currencies.convert(
                    item.monthly_amount, item.currency_code or _RUB, _RUB
                )
                if item.monthly_amount is not None
                else None
            )
        return item

    async def archive_recurring(
        self, recurring_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        item = await self.get_recurring(recurring_id, user_id)
        item.is_archived = True

    async def generate_from_categories(
        self, user_id: uuid.UUID
    ) -> list[RecurringExpense]:
        date_from, date_to = _recent_window()
        spend = await self._repo.required_spend_by_category(
            user_id, date_from, date_to
        )
        existing = await self._repo.list_active(user_id)
        existing_categories = {item.category_id for item in existing}
        categories = {
            c.id: c for c in await self._categories.list_active(user_id)
        }

        created: list[RecurringExpense] = []
        for category_id, signed_total in spend.items():
            if category_id in existing_categories:
                continue
            category = categories.get(category_id)
            if category is None or category.kind != CategoryKind.EXPENSE:
                continue
            monthly = (abs(signed_total) / _MONTHS_WINDOW).quantize(
                _CENTS, rounding=ROUND_HALF_UP
            )
            if monthly <= 0:
                continue
            created.append(
                await self._repo.add(
                    RecurringExpense(
                        user_id=user_id,
                        required=RequiredKind.REQUIRED,
                        category_id=category_id,
                        name=category.name,
                        monthly_amount=monthly,
                        currency_code=_RUB,
                        amount_rub=monthly,
                        comments=None,
                    )
                )
            )
        return created

    async def _validate_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        category = await self._categories.get(category_id, user_id)
        if category is None:
            raise NotFoundError("Категория не найдена.")
        if category.is_archived:
            raise ValidationFailedError("Категория в архиве.")
        if category.kind != CategoryKind.EXPENSE:
            raise ValidationFailedError(
                "План-минимум ведётся только по расходным категориям."
            )


def _recent_window() -> tuple[datetime, datetime]:
    """Окно из последних _MONTHS_WINDOW полных месяцев в UTC.

    Возвращает (начало, конец-исключительно): от первого числа
    месяца N назад до первого числа текущего месяца.
    """
    now = datetime.now(UTC)
    end = datetime(now.year, now.month, 1, tzinfo=UTC)
    year, month = now.year, now.month - _MONTHS_WINDOW
    while month <= 0:
        month += 12
        year -= 1
    start = datetime(year, month, 1, tzinfo=UTC)
    return start, end
