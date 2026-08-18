"""Сборка альбома в одну пачку.

Телеграм присылает альбом не одним сообщением, а несколькими — по
одному на файл. Обрабатывать их по отдельности неверно дважды: модель
не видит выписки рядом и не может свести их между собой, а сайт
получает столько же одновременных запросов, сколько файлов, и
отвечает таймаутом.

Первое сообщение группы ждёт остальные и забирает всю пачку; другие
сразу возвращают None — их обработает первое.
"""

import asyncio
from typing import Any

__all__ = ["AlbumBuffer"]

# Телеграм отправляет альбом одним пакетом, задержка нужна только на
# разброс доставки. Полторы секунды с запасом, но не заметно.
DEFAULT_DELAY = 1.5


class AlbumBuffer:
    def __init__(self, delay: float = DEFAULT_DELAY) -> None:
        self._delay = delay
        self._groups: dict[str, list[Any]] = {}

    async def collect(
        self, group_id: str | None, message: Any
    ) -> list[Any] | None:
        """Вернуть пачку целиком или None, если её заберёт другой.

        Сообщение без ``group_id`` — не альбом, отдаём как пачку из
        одного: вызывающему не нужно знать разницу.
        """
        if group_id is None:
            return [message]

        waiting = self._groups.get(group_id)
        if waiting is not None:
            waiting.append(message)
            return None

        self._groups[group_id] = [message]
        await asyncio.sleep(self._delay)
        batch: list[Any] = self._groups.pop(group_id, [message])
        return batch
