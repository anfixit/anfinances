"""Общие схемы ответов API.

Единый формат по §24 стандартов: успех всегда завёрнут в
``ApiResponse`` (``data`` + ``meta``), ошибка — плоский
``ErrorResponse`` (``code`` + ``message`` + ``details``).

Доменные схемы (модели сущностей) живут в ``domains/*/schemas.py``.
Здесь — только кросс-доменный конверт ответа.
"""

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "ApiResponse",
    "ErrorDetail",
    "ErrorResponse",
    "PaginationMeta",
]


class PaginationMeta(BaseModel):
    """Метаданные пагинации для списочных ответов."""

    page: int = Field(ge=1)
    per_page: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class ApiResponse[T](BaseModel):
    """Обёртка для всех успешных ответов.

    ``data`` — полезная нагрузка (объект или список).
    ``meta`` — произвольные метаданные (например, пагинация).
    Пустой ``meta`` по умолчанию, чтобы клиент всегда читал
    предсказуемую структуру.
    """

    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    """Деталь ошибки по конкретному полю.

    ``field`` = None для общих ошибок, не привязанных к полю.
    """

    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    """Единый формат ошибки (без обёртки).

    ``code`` — машиночитаемый код в UPPER_SNAKE.
    ``message`` — человекочитаемое сообщение.
    ``details`` — список ошибок по полям (может быть пустым).
    """

    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
