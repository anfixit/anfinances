"""Лимит запросов на одно подключение ИИ.

Скользящее окно в памяти процесса — как и slowapi для входа
(ADR-026): бэкенд живёт одним воркером, общий Redis не нужен.
Ключ — подключение, а не IP: ассистенты ходят с серверов
вендора, и по IP все пользователи одного вендора слились бы в
одного.
"""

import time
import uuid
from collections import deque

__all__ = ["ConnectionRateLimiter", "connection_limiter"]

_WINDOW_SECONDS = 60.0


class ConnectionRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[uuid.UUID, deque[float]] = {}

    def hit(self, connection_id: uuid.UUID, per_minute: int) -> bool:
        """Учесть запрос. False — лимит исчерпан, запрос не пускать."""
        if per_minute <= 0:
            return True
        now = time.monotonic()
        hits = self._hits.setdefault(connection_id, deque())
        while hits and hits[0] <= now - _WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= per_minute:
            return False
        hits.append(now)
        self._prune(now)
        return True

    def reset(self) -> None:
        self._hits.clear()

    def _prune(self, now: float) -> None:
        # Подключения, которые давно молчат, не должны копиться.
        if len(self._hits) < 1024:
            return
        stale = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] <= now - _WINDOW_SECONDS
        ]
        for key in stale:
            del self._hits[key]


connection_limiter = ConnectionRateLimiter()
