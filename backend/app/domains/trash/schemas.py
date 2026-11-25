"""Pydantic-схемы корзины. Сами строки (payload) наружу не отдаются."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

__all__ = ["DeletedRecordRead", "DeletedResult"]


class DeletedRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    summary: str
    source: str
    deleted_at: datetime
    restored_at: datetime | None


class DeletedResult(BaseModel):
    """Ответ роута удаления: что удалено и где его искать."""

    status: str = "deleted"
    trash_id: uuid.UUID
    summary: str
