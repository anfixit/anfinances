"""Бизнес-логика сверки счёта.

Порядок такой: сначала показать расхождение, потом уже закрывать.
Автоматическая корректировка без показа превратила бы сверку в
машинку, которая молча подгоняет остаток под банк, — а смысл ровно
обратный: увидеть, что записано не то.

Корректировка — последнее средство и делается явным флагом. Обычный
путь: увидеть расхождение, найти задвоенную или пропавшую операцию,
исправить её и свериться заново.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums import TransactionKind
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.domains.accounts.repository import AccountRepository
from app.domains.categories.repository import CategoryRepository
from app.domains.reconciliation.models import Reconciliation
from app.domains.reconciliation.repository import ReconciliationRepository
from app.domains.reconciliation.schemas import ReconcileRequest
from app.domains.transactions.schemas import TransactionCreate
from app.domains.transactions.service import TransactionService

__all__ = ["ReconciliationResult", "ReconciliationService"]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Расхождение между банком и записанным."""

    account_id: uuid.UUID
    date: datetime
    statement_balance: Decimal
    computed_balance: Decimal
    difference: Decimal
    unreconciled_count: int


class ReconciliationService:
    def __init__(
        self,
        repo: ReconciliationRepository,
        accounts: AccountRepository,
        categories: CategoryRepository,
        transactions: TransactionService,
    ) -> None:
        self._repo = repo
        self._accounts = accounts
        self._categories = categories
        self._transactions = transactions

    async def preview(
        self, account_id: uuid.UUID, user_id: uuid.UUID, data: ReconcileRequest
    ) -> ReconciliationResult:
        account = await self._accounts.get(account_id, user_id)
        if account is None:
            raise NotFoundError("Счёт не найден.")

        total = await self._repo.balance_at(account_id, user_id, data.date)
        computed = account.initial_balance + total
        return ReconciliationResult(
            account_id=account_id,
            date=data.date,
            statement_balance=data.statement_balance,
            computed_balance=computed,
            # Плюс — банк богаче записанного: не хватает дохода или
            # записан лишний расход.
            difference=data.statement_balance - computed,
            unreconciled_count=await self._repo.unreconciled_count(
                account_id, user_id, data.date
            ),
        )

    async def reconcile(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReconcileRequest,
        now: datetime | None = None,
    ) -> Reconciliation:
        await self._repo.lock_account(account_id, user_id)
        result = await self.preview(account_id, user_id, data)

        if (
            data.adjust
            and data.expected_difference is not None
            and data.expected_difference != result.difference
        ):
            raise ValidationFailedError(
                f"Пока вы смотрели, остаток изменился: расхождение теперь "
                f"{result.difference}, а не {data.expected_difference}. "
                f"Проверьте ещё раз."
            )
        if result.difference != 0 and not data.adjust:
            raise ValidationFailedError(
                f"Расхождение {result.difference}. Найдите пропавшую или "
                f"задвоенную операцию, либо повторите с adjust=true — "
                f"тогда разницу закроет корректирующая операция."
            )

        adjustment_id: uuid.UUID | None = None
        if result.difference != 0:
            await self._refuse_backdated(account_id, user_id, data.date)
            adjustment_id = await self._adjust(
                account_id, user_id, data, result.difference
            )

        stamp = now or datetime.now(UTC)
        await self._repo.mark_reconciled(account_id, user_id, data.date, stamp)
        return await self._repo.add(
            Reconciliation(
                user_id=user_id,
                account_id=account_id,
                date=data.date,
                statement_balance=data.statement_balance,
                computed_balance=result.computed_balance,
                adjustment_transaction_id=adjustment_id,
            )
        )

    async def _refuse_backdated(
        self, account_id: uuid.UUID, user_id: uuid.UUID, moment: datetime
    ) -> None:
        """Корректировка не может лечь раньше последней сверки.

        Иначе она сдвинет остаток и на дату той сверки: сошедшийся
        когда-то счёт молча перестанет сходиться, а отметки на
        операциях продолжат говорить, что всё проверено.
        """
        latest = (await self._repo.latest_per_account(user_id)).get(account_id)
        if latest is None:
            return
        if latest.tzinfo is None:
            # SQLite в тестах отдаёт время без зоны; храним мы UTC.
            latest = latest.replace(tzinfo=UTC)
        if moment < latest:
            raise ValidationFailedError(
                f"Счёт уже сверен по {latest:%d.%m.%Y}. Корректировка "
                f"задним числом сломает ту сверку — сверьте на дату не "
                f"раньше или найдите расхождение в операциях."
            )

    async def _adjust(
        self,
        account_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReconcileRequest,
        difference: Decimal,
    ) -> uuid.UUID:
        """Операция, закрывающая расхождение.

        Корректировка — не доход и не трата, а правка учёта: в графики
        доходов и расходов она не попадает. Раньше тут создавался доход
        или расход, и каждая сверка искажала месячные итоги. Знак —
        само направление разницы.
        """
        tx = await self._transactions.create_transaction(
            user_id,
            TransactionCreate(
                account_id=account_id,
                kind=TransactionKind.ADJUSTMENT,
                amount=difference,
                date=data.date,
                comment="Корректировка по сверке с банком",
            ),
        )
        return tx.id

    async def history(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Reconciliation]:
        if await self._accounts.get(account_id, user_id) is None:
            raise NotFoundError("Счёт не найден.")
        return await self._repo.history(account_id, user_id)
