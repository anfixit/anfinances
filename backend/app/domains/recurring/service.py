"""Бизнес-логика домена recurring (план-минимум).

Регулярные обязательные траты по расходным категориям.
``amount_rub`` запекается при создании/обновлении из
``monthly_amount`` по текущему курсу (как в transactions);
при сильном движении курса обновляется пере-сохранением.
Удаление — архивирование (ADR-010).

Генератор строит предварительный план по последним полным месяцам.
Если у родительской категории нет существующей детализации, он
предлагает общий конверт родителя. Если часть подкатегорий уже есть
в плане, генератор предлагает только недостающие подкатегории и не
создаёт конфликтующий план родителя.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal

from app.core.datetime import (
    DEFAULT_TIMEZONE,
    recent_full_months_utc,
)
from app.core.enums import CategoryKind, RequiredKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.categories.models import Category
from app.domains.categories.repository import CategoryRepository
from app.domains.currencies.service import CurrencyService
from app.domains.recurring.models import RecurringExpense
from app.domains.recurring.repository import RecurringRepository
from app.domains.recurring.schemas import (
    RecurringCreate,
    RecurringGenerationProposal,
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

    async def preview_generation(
        self,
        user_id: uuid.UUID,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> list[RecurringGenerationProposal]:
        date_from, date_to = recent_full_months_utc(
            _MONTHS_WINDOW,
            timezone_name,
        )
        spend = await self._repo.required_spend_by_category(
            user_id,
            date_from,
            date_to,
        )
        existing = await self._repo.list_active(user_id)
        existing_categories = {item.category_id for item in existing}
        categories = [
            category
            for category in await self._categories.list_active(user_id)
            if category.kind == CategoryKind.EXPENSE
        ]
        return self._build_generation_proposals(
            categories,
            spend,
            existing_categories,
        )

    async def generate_from_categories(
        self,
        user_id: uuid.UUID,
        category_ids: list[uuid.UUID],
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> list[RecurringExpense]:
        proposals = await self.preview_generation(user_id, timezone_name)
        proposals_by_id = {
            proposal.category_id: proposal for proposal in proposals
        }
        unavailable = [
            category_id
            for category_id in category_ids
            if category_id not in proposals_by_id
        ]
        if unavailable:
            raise ValidationFailedError(
                "Часть выбранных категорий больше недоступна для генерации."
            )

        created: list[RecurringExpense] = []
        for category_id in category_ids:
            proposal = proposals_by_id[category_id]
            created.append(
                await self._repo.add(
                    RecurringExpense(
                        user_id=user_id,
                        required=RequiredKind.REQUIRED,
                        category_id=proposal.category_id,
                        name=proposal.category_name,
                        monthly_amount=proposal.monthly_amount,
                        currency_code=_RUB,
                        amount_rub=proposal.monthly_amount,
                        comments=None,
                    )
                )
            )
        return created

    def _build_generation_proposals(
        self,
        categories: list[Category],
        spend: dict[uuid.UUID, Decimal],
        existing_categories: set[uuid.UUID],
    ) -> list[RecurringGenerationProposal]:
        categories_by_id = {category.id: category for category in categories}
        children_by_parent: dict[uuid.UUID, list[Category]] = {}
        roots: list[Category] = []

        for category in categories:
            if category.parent_id is None:
                roots.append(category)
                continue
            children_by_parent.setdefault(category.parent_id, []).append(
                category
            )

        proposals: list[RecurringGenerationProposal] = []
        for root in sorted(roots, key=lambda item: item.name.casefold()):
            children = sorted(
                children_by_parent.get(root.id, []),
                key=lambda item: item.name.casefold(),
            )
            if root.id in existing_categories:
                continue

            existing_children = [
                child for child in children if child.id in existing_categories
            ]
            if existing_children:
                for child in children:
                    if child.id in existing_categories:
                        continue
                    proposal = self._proposal_for_category(
                        child,
                        spend.get(child.id, Decimal(0)),
                        root.name,
                    )
                    if proposal is not None:
                        proposals.append(proposal)
                continue

            total = spend.get(root.id, Decimal(0))
            total += sum(
                (spend.get(child.id, Decimal(0)) for child in children),
                start=Decimal(0),
            )
            proposal = self._proposal_for_category(root, total)
            if proposal is not None:
                proposals.append(proposal)

        orphan_categories = [
            category
            for category in categories
            if category.parent_id is not None
            and category.parent_id not in categories_by_id
        ]
        for category in sorted(
            orphan_categories,
            key=lambda item: item.name.casefold(),
        ):
            if category.id in existing_categories:
                continue
            proposal = self._proposal_for_category(
                category,
                spend.get(category.id, Decimal(0)),
            )
            if proposal is not None:
                proposals.append(proposal)

        return proposals

    def _proposal_for_category(
        self,
        category: Category,
        signed_total: Decimal,
        parent_name: str | None = None,
    ) -> RecurringGenerationProposal | None:
        monthly = (abs(signed_total) / _MONTHS_WINDOW).quantize(
            _CENTS,
            rounding=ROUND_HALF_UP,
        )
        if monthly <= 0:
            return None
        category_path = (
            category.name
            if parent_name is None
            else f"{parent_name} → {category.name}"
        )
        return RecurringGenerationProposal(
            category_id=category.id,
            category_name=category.name,
            category_path=category_path,
            monthly_amount=monthly,
        )

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
