"""Фоновое обновление курсов валют.

Обновление на старте приложения, кнопка на странице валют и ручной
POST /currencies/rates/refresh остаются как были; здесь добавляется
только периодический прогон, чтобы долгоживущий контейнер не работал
с курсом дня своего запуска.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger("anfinances.currencies.scheduler")

__all__ = ["refresh_rates_periodically"]

Refresher = Callable[[], Awaitable[None]]


async def refresh_rates_periodically(
    refresh: Refresher,
    interval_seconds: float,
) -> None:
    """Вызывать ``refresh`` каждые ``interval_seconds`` секунд.

    Ошибка провайдера логируется и не прерывает цикл: отсутствие
    свежего курса — не повод останавливать обновление навсегда.
    Отмена задачи пробрасывается наружу без перехвата.
    """
    while True:
        try:
            await refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Periodic rates refresh failed", exc_info=True)
        await asyncio.sleep(interval_seconds)
