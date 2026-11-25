"""Pydantic-схемы домена categories."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import CategoryKind
from app.core.schemas import reject_nulls

__all__ = ["CategoryCreate", "CategoryRead", "CategoryUpdate"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: CategoryKind
    parent_id: uuid.UUID | None = None
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    icon: str | None = Field(default=None, max_length=64)
    sort_order: int | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "CategoryUpdate":
        reject_nulls(self, ("name", "sort_order"))
        return self


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: CategoryKind
    parent_id: uuid.UUID | None
    icon: str | None
    sort_order: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime
