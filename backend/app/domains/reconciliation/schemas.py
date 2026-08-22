"""Pydantic-схемы домена reconciliation."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ReconciliationPreview",
    "ReconciliationRead",
    "ReconcileRequest",
]


class ReconcileRequest(BaseModel):
    # Остаток из банка. Может быть отрицательным: по кредитке это
    # норма, и запрещать минус значило бы сломать сверку кредиток.
    statement_balance: Decimal
    date: datetime
    # Закрыть расхождение корректирующей операцией. По умолчанию нет:
    # сначала надо поискать пропавшую или задвоенную запись, а
    # корректировка — последнее средство.
    adjust: bool = False
    adjustment_category_id: uuid.UUID | None = None


class ReconciliationPreview(BaseModel):
    account_id: uuid.UUID
    date: datetime
    statement_balance: Decimal
    computed_balance: Decimal
    difference: Decimal
    # Сколько операций попадёт под отметку сверки.
    unreconciled_count: int


class ReconciliationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    date: datetime
    statement_balance: Decimal
    computed_balance: Decimal
    adjustment_transaction_id: uuid.UUID | None
    created_at: datetime
