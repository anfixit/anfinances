"""Отметка «бот на связи» и проверка для healthcheck контейнера.

Процесс бота остаётся жив и тогда, когда работать не может. Главный
случай — смена пароля на сайте: бот входит по ``SINGLE_USER_PASSWORD``,
после смены вход перестаёт проходить, но aiogram продолжает опрашивать
телеграм, ``restart: always`` перезапускать нечего, и docker считает
контейнер здоровым. Узнать о поломке можно было только написав боту и
не дождавшись ответа.

Поэтому бот раз в минуту спрашивает у сайта ``/auth/me`` и, если тот
его пускает, обновляет отметку. Healthcheck просто смотрит на возраст
отметки — лишнего входа он не делает, Argon2 на сервере с гигабайтом
памяти стоит дорого.

Запуск проверки: ``python -m anfinances_bot.health`` (код 0 — живой,
1 — отметка протухла или её нет). Путь берётся из ``BOT_STATE_PATH``,
рядом с ``state.json`` и ``spend.json``.
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("anfinances_bot.health")

__all__ = [
    "HEARTBEAT_EVERY",
    "MAX_AGE",
    "health_path",
    "is_fresh",
    "run_health_loop",
    "touch",
]

# Раз в минуту. Чаще незачем: проверка нужна, чтобы заметить поломку
# за минуты, а не за секунды.
HEARTBEAT_EVERY = 60.0

# Сколько отметка считается свежей. Две-три пропущенные проверки — это
# ещё не поломка: сайт мог перезапускаться деплоем.
MAX_AGE = timedelta(minutes=5)


class _Pingable(Protocol):
    """То, что умеет спросить сайт, жив ли доступ."""

    async def me(self) -> object: ...


def health_path(state_path: str | None = None) -> Path:
    """Файл отметки — рядом с состоянием бота."""
    raw = state_path or os.environ.get("BOT_STATE_PATH", "/data/state.json")
    return Path(raw).with_name("health.txt")


def touch(path: Path, now: datetime | None = None) -> None:
    """Записать время удачной проверки."""
    moment = now or datetime.now(UTC)
    path.write_text(moment.isoformat(), encoding="utf-8")


def is_fresh(
    path: Path,
    max_age: timedelta = MAX_AGE,
    now: datetime | None = None,
) -> bool:
    """Отметка есть и ей меньше ``max_age``.

    Нечитаемая или битая отметка — то же самое, что её отсутствие:
    по ней нельзя сказать, что бот работает.
    """
    try:
        stamp = datetime.fromisoformat(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - stamp < max_age


async def run_health_loop(
    client: _Pingable,
    path: Path,
    interval: float = HEARTBEAT_EVERY,
) -> None:
    """Обновлять отметку, пока сайт пускает бота.

    Неудача отметку не трогает и цикл не роняет: пару минут сайт может
    быть недоступен из-за деплоя. Если не пускает дольше ``MAX_AGE``,
    отметка протухнет сама, и контейнер станет unhealthy.
    """
    while True:
        try:
            await client.me()
            touch(path)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Сайт не пускает бота", exc_info=True)
        await asyncio.sleep(interval)


def main() -> int:
    return 0 if is_fresh(health_path()) else 1


if __name__ == "__main__":
    sys.exit(main())
