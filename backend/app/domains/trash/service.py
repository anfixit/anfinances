"""Корзина: что удалено — лежит здесь и возвращается как было.

Копию снимает роут удаления до вызова доменного сервиса, в той же
транзакции БД: удаление и запись в корзину либо случаются вместе,
либо не случаются вовсе. Доменные сервисы о корзине не знают — так
она ловит любое удаление: с сайта, из бота, от ассистента.

Возврат вставляет строки обратно с теми же id. Платёж по кредиту
при этом снова гасит тело — ровно то, что вернуло его удаление.

Ассистенту сверенное удалять нельзя: отметка сверки — решение
человека над выпиской банка.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.enums import TransactionKind
from app.core.exceptions import (
    AlreadyExistsError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from app.core.models import Base
from app.domains.accounts.models import Account
from app.domains.credits.models import CreditPayment
from app.domains.transactions.models import Transaction, Transfer
from app.domains.trash.models import DeletedRecord
from app.domains.trash.repository import REFERENCED, TrashRepository
from app.domains.trash.snapshot import dump, load

__all__ = ["Deleter", "TrashService"]

_MODELS: dict[str, type[Base]] = {
    "transfers": Transfer,
    "transactions": Transaction,
    "credit_payments": CreditPayment,
}

_KIND_LABELS = {
    TransactionKind.EXPENSE: "Трата",
    TransactionKind.INCOME: "Доход",
    TransactionKind.REFUND: "Возврат",
    TransactionKind.LOAN: "Получение кредита",
    TransactionKind.ADJUSTMENT: "Корректировка",
    TransactionKind.TRANSFER: "Перевод",
    TransactionKind.CREDIT_PAYMENT: "Платёж по кредиту",
}

_RECONCILED = (
    "Операция сверена с банком — ИИ-интеграции сверенное не удаляют. "
    "Если это действительно ошибка, удалите её на сайте."
)


@dataclass(frozen=True)
class Deleter:
    """Кто удаляет: человек на сайте или ассистент."""

    source: str
    ai: bool = False
    ai_connection_id: uuid.UUID | None = None


class TrashService:
    def __init__(self, repo: TrashRepository, timezone: str = "UTC") -> None:
        self._repo = repo
        try:
            self._tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            self._tz = ZoneInfo("UTC")

    # --- в корзину -----------------------------------------------

    async def keep_transaction(
        self, tx_id: uuid.UUID, user_id: uuid.UUID, who: Deleter
    ) -> DeletedRecord:
        tx = await self._repo.get_transaction(tx_id, user_id)
        if tx is None:
            raise NotFoundError("Операция не найдена.")
        if who.ai and tx.reconciled_at is not None:
            raise ForbiddenError(_RECONCILED)
        return await self._keep(
            user_id,
            who,
            kind="transaction",
            summary=self._tx_summary(tx),
            rows=[("transactions", tx)],
        )

    async def keep_transfer(
        self, transfer_id: uuid.UUID, user_id: uuid.UUID, who: Deleter
    ) -> DeletedRecord:
        transfer, legs = await self._repo.get_transfer(transfer_id, user_id)
        if transfer is None:
            raise NotFoundError("Перевод не найден.")
        if who.ai and any(leg.reconciled_at is not None for leg in legs):
            raise ForbiddenError(_RECONCILED)
        return await self._keep(
            user_id,
            who,
            kind="transfer",
            summary=self._transfer_summary(legs),
            rows=[("transfers", transfer)]
            + [("transactions", leg) for leg in legs],
        )

    async def keep_credit_payment(
        self,
        credit_id: uuid.UUID,
        payment_id: uuid.UUID,
        user_id: uuid.UUID,
        who: Deleter,
    ) -> DeletedRecord:
        payment = await self._repo.get_payment(payment_id, user_id)
        if payment is None or payment.credit_id != credit_id:
            raise NotFoundError("Платёж не найден.")
        tx = (
            await self._repo.get_transaction(payment.transaction_id, user_id)
            if payment.transaction_id is not None
            else None
        )
        if who.ai and tx is not None and tx.reconciled_at is not None:
            raise ForbiddenError(_RECONCILED)
        credit = await self._repo.get_credit(credit_id, user_id)
        name = credit.name if credit is not None else "?"
        rows: list[tuple[str, Base]] = []
        if tx is not None:
            rows.append(("transactions", tx))
        rows.append(("credit_payments", payment))
        summary = (
            f"Платёж по кредиту «{name}»: "
            f"{_money(payment.total_amount)} {payment.currency_code} "
            f"(тело {_money(payment.principal_amount)}, проценты "
            f"{_money(payment.interest_amount)}) · "
            f"{self._day(payment.date)}"
        )
        return await self._keep(
            user_id,
            who,
            kind="credit_payment",
            summary=summary,
            rows=rows,
            extra={
                "credit_id": str(credit_id),
                "principal_amount": str(payment.principal_amount),
            },
        )

    # --- из корзины ----------------------------------------------

    async def list_waiting(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[DeletedRecord]:
        return await self._repo.list_waiting(user_id, limit)

    async def restore(
        self, record_id: uuid.UUID, user_id: uuid.UUID
    ) -> DeletedRecord:
        record = await self._repo.get(record_id, user_id)
        if record is None:
            raise NotFoundError("В корзине такой записи нет.")
        if record.restored_at is not None:
            raise ValidationFailedError("Эта запись уже возвращена.")

        rows = [
            (_MODELS[item["table"]], dict(item["values"]))
            for item in record.payload["rows"]
        ]
        for model, values in rows:
            if await self._repo.exists(model, uuid.UUID(values["id"])):
                raise AlreadyExistsError(
                    "Эта запись уже на месте — возвращать нечего."
                )
            await self._check_references(values, user_id)

        if record.kind == "credit_payment":
            await self._take_principal_again(record.payload, user_id)

        for model, values in rows:
            await self._repo.insert(load(model, values))
        record.restored_at = datetime.now(UTC)
        return record

    # --- внутреннее ----------------------------------------------

    async def _keep(
        self,
        user_id: uuid.UUID,
        who: Deleter,
        *,
        kind: str,
        summary: str,
        rows: list[tuple[str, Base]],
        extra: dict[str, Any] | None = None,
    ) -> DeletedRecord:
        payload: dict[str, Any] = {
            "rows": [
                {"table": table, "values": dump(row)} for table, row in rows
            ],
            **(extra or {}),
        }
        return await self._repo.add(
            DeletedRecord(
                id=uuid.uuid4(),
                user_id=user_id,
                kind=kind,
                summary=summary,
                payload=payload,
                source=who.source,
                ai_connection_id=who.ai_connection_id,
                deleted_at=datetime.now(UTC),
            )
        )

    async def _check_references(
        self, values: dict[str, Any], user_id: uuid.UUID
    ) -> None:
        """Счёт обязан быть на месте; категорию и получателя — терпим.

        Категории и получатели могли объединить или убрать. Имена
        остались в снимках строки, так что без ссылки операция
        по-прежнему читается — лучше вернуть её так, чем не вернуть.
        """
        for key, model in REFERENCED.items():
            raw = values.get(key)
            if raw is None:
                continue
            if await self._repo.owns(model, uuid.UUID(raw), user_id):
                continue
            if model is Account:
                raise ValidationFailedError(
                    "Счёта, на котором была операция, больше нет — "
                    "вернуть её некуда."
                )
            values[key] = None

    async def _take_principal_again(
        self, payload: dict[str, Any], user_id: uuid.UUID
    ) -> None:
        credit = await self._repo.get_credit(
            uuid.UUID(payload["credit_id"]), user_id, for_update=True
        )
        if credit is None:
            raise ValidationFailedError(
                "Кредита, к которому относился платёж, больше нет."
            )
        principal = Decimal(payload["principal_amount"])
        if principal > credit.principal_balance:
            raise ValidationFailedError(
                f"По кредиту «{credit.name}» осталось "
                f"{_money(credit.principal_balance)} "
                f"{credit.currency_code}, а платёж гасит "
                f"{_money(principal)}: он не помещается. Похоже, после "
                "удаления этот платёж записали заново."
            )
        credit.principal_balance -= principal

    def _tx_summary(self, tx: Transaction) -> str:
        label = _KIND_LABELS.get(tx.kind, str(tx.kind))
        parts = [
            f"{label} {_money(abs(tx.amount))} {tx.currency_code}",
            tx.account_name_snapshot or "",
            " → ".join(
                p
                for p in (
                    tx.category_name_snapshot,
                    tx.subcategory_name_snapshot,
                )
                if p
            ),
            tx.payee_name_snapshot or "",
            f"«{tx.comment}»" if tx.comment else "",
            self._day(tx.date),
        ]
        return " · ".join(p for p in parts if p)

    def _transfer_summary(self, legs: list[Transaction]) -> str:
        moves = [x for x in legs if x.kind == TransactionKind.TRANSFER]
        out = next((x for x in moves if x.amount < 0), None)
        into = next((x for x in moves if x.amount > 0), None)
        fee = next(
            (x for x in legs if x.kind == TransactionKind.EXPENSE), None
        )
        if out is None or into is None:
            return "Перевод (повреждённый)"
        text = (
            f"Перевод {out.account_name_snapshot} → "
            f"{into.account_name_snapshot}: "
            f"{_money(-out.amount)} {out.currency_code}"
        )
        if into.currency_code != out.currency_code:
            text += f" → {_money(into.amount)} {into.currency_code}"
        if fee is not None:
            text += f", комиссия {_money(-fee.amount)}"
        if out.comment:
            text += f" · «{out.comment}»"
        return f"{text} · {self._day(out.date)}"

    def _day(self, moment: datetime) -> str:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(self._tz).strftime("%d.%m.%Y")


def _money(value: Decimal) -> str:
    return f"{value:.2f}"
