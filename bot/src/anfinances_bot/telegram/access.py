"""Белый список Telegram-ID.

Юзернейм бота угадывается. Без этой проверки любой, кто набредёт на
бота, сможет читать финансы и писать операции. Отсечка происходит до
распознавания речи и до обращения к модели — чужой запрос не стоит
ни копейки и ничего не раскрывает.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware

logger = logging.getLogger("anfinances_bot.access")

__all__ = ["AllowlistMiddleware"]

_DENIED = "Этот бот личный. Доступ только у владельца."


class AllowlistMiddleware(BaseMiddleware):
    def __init__(self, allowed: frozenset[int]) -> None:
        self._allowed = allowed

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if user_id in self._allowed:
            return await handler(event, data)

        logger.warning("Отклонён доступ, telegram_id=%s", user_id)
        answer = getattr(event, "answer", None)
        if answer is not None:
            await answer(_DENIED)
        return None
