"""Кастомные исключения приложения и FastAPI-обработчики.

Формат ошибок единый (см. ARCHITECTURE.md §7):
{
  "error": {
    "code": "validation_failed",
    "message": "...",
    "details": [...]
  }
}
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── Доменные исключения ──────────────────────────────────────────────


class AppException(Exception):
    """Базовое исключение приложения.

    Все доменные ошибки наследуются от него. У каждого — стабильный code
    (для клиента), HTTP-статус, человекочитаемое сообщение и опциональные details.
    """

    code: str = "internal_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or []
        super().__init__(self.message)


class NotFoundError(AppException):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "Resource not found"


class ValidationFailedError(AppException):
    code = "validation_failed"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "Validation failed"


class UnauthorizedError(AppException):
    code = "unauthorized"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Authentication required"


class ForbiddenError(AppException):
    code = "forbidden"
    status_code = status.HTTP_403_FORBIDDEN
    message = "Operation not permitted"


class ConflictError(AppException):
    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "Resource conflict"


# ── Хелпер для формата ответа ────────────────────────────────────────


def _error_response(
    code: str,
    message: str,
    status_code: int,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


# ── Регистрация обработчиков на уровне FastAPI ───────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Подключает обработчики исключений к FastAPI-приложению."""

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return _error_response(exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Переупаковываем Pydantic-ошибки в наш формат.
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p != "body"),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return _error_response(
            "validation_failed",
            "Validation failed",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Стандартные HTTPException от FastAPI/Starlette (например, 404 на роуте)
        # тоже приводим к единому формату.
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            422: "validation_failed",
        }
        return _error_response(
            code_map.get(exc.status_code, "error"),
            str(exc.detail),
            exc.status_code,
        )
