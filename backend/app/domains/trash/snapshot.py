"""Строка ORM ↔ JSON без потерь.

Деньги — Decimal строкой, чтобы 4312.04 не стало 4312.0399999.
Даты — ISO с часовым поясом, id — строкой UUID, перечисления — их
значением. Обратно тип берётся из колонки модели, а не угадывается
по виду строки.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Enum as SaEnum
from sqlalchemy import inspect

from app.core.models import Base

__all__ = ["dump", "load"]


def dump(row: Base) -> dict[str, Any]:
    """Все колонки строки — JSON-совместимыми значениями."""
    mapper = inspect(row).mapper
    return {
        attr.key: _encode(getattr(row, attr.key))
        for attr in mapper.column_attrs
    }


def load[M: Base](model: type[M], values: dict[str, Any]) -> M:
    """Собрать новую строку модели из того, что дал ``dump``."""
    mapper = inspect(model)
    kwargs: dict[str, Any] = {}
    for attr in mapper.column_attrs:
        if attr.key not in values:
            continue
        raw = values[attr.key]
        kwargs[attr.key] = (
            None if raw is None else _decode(attr.columns[0].type, raw)
        )
    return model(**kwargs)


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal | uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Не умею сохранить {type(value).__name__} в корзину")


def _decode(sa_type: Any, raw: Any) -> Any:
    if isinstance(sa_type, SaEnum) and sa_type.enum_class is not None:
        return sa_type.enum_class(raw)
    python_type = sa_type.python_type
    if python_type is datetime:
        return datetime.fromisoformat(raw)
    if python_type is date:
        return date.fromisoformat(raw)
    if python_type in (Decimal, uuid.UUID):
        return python_type(raw)
    return raw
