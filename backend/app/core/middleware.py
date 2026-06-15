"""Middleware: security-заголовки, CORS и request logging.

Подключается в main.py при создании FastAPI-приложения.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings

logger = logging.getLogger("anfinances.request")

# Security-заголовки уровня приложения. HSTS сознательно НЕ ставим
# здесь — им владеет TLS-терминатор (nginx), иначе на http-dev был бы
# бессмысленный заголовок, а на проде — дубль. CSP для JSON-API
# максимально строгий: ничего грузить не нужно.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": ("default-src 'none'; frame-ancestors 'none'"),
}


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Подключает middleware к FastAPI-приложению.

    Порядок важен: middleware выполняются в обратном порядке
    регистрации (последний добавленный — первый на запрос).
    CORS должен быть внешним.
    """

    # Логирование запросов + security-заголовки (внутренний слой).
    @app.middleware("http")
    async def _logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Прокидываем request_id в request.state — пригодится
        # для логов в сервисах.
        request.state.request_id = request_id

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s -> %d (%.1fms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        response.headers["X-Request-ID"] = request_id
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    # CORS (внешний слой — добавляется последним, отрабатывает
    # первым). При allow_credentials=True перечисляем методы и
    # заголовки явно (§8.5): wildcard с credentials небезопасен.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
