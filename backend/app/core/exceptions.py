"""Кастомные исключения приложения и FastAPI-обработчики.

Единый формат ошибок (см. ARCHITECTURE.md §7, ADR-014):

    {
      "code": "NOT_FOUND",
      "message": "...",
      "details": [{"field": "...", "message": "..."}]
    }
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)

from app.core.schemas import ErrorDetail, ErrorResponse


class AppException(Exception):
    """Базовое исключение приложения.

    Все доменные ошибки наследуются от него. У каждого —
    стабильный code (UPPER_SNAKE, для клиента), HTTP-статус,
    человекочитаемое сообщение и опциональные details.
    """

    code: str = "INTERNAL_ERROR"
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
    code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND
    message = "Resource not found"


class ValidationFailedError(AppException):
    code = "VALIDATION_ERROR"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "Validation failed"


class UnauthorizedError(AppException):
    code = "UNAUTHORIZED"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Authentication required"


class ForbiddenError(AppException):
    code = "FORBIDDEN"
    status_code = status.HTTP_403_FORBIDDEN
    message = "Operation not permitted"


class AlreadyExistsError(AppException):
    code = "ALREADY_EXISTS"
    status_code = status.HTTP_409_CONFLICT
    message = "Resource already exists"


def _error_response(
    code: str,
    message: str,
    status_code: int,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        details=[ErrorDetail.model_validate(d) for d in (details or [])],
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Подключает обработчики исключений к приложению."""

    @app.exception_handler(AppException)
    async def _app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        return _error_response(
            exc.code,
            exc.message,
            exc.status_code,
            exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p != "body"),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return _error_response(
            "VALIDATION_ERROR",
            "Validation failed",
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details,
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return _error_response(
            "RATE_LIMITED",
            "Слишком много запросов. Попробуйте позже.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "ALREADY_EXISTS",
            422: "VALIDATION_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }
        return _error_response(
            code_map.get(exc.status_code, "INTERNAL_ERROR"),
            str(exc.detail),
            exc.status_code,
        )
