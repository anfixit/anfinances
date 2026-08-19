"""Состояние проактивных напоминаний между перезапусками.

Отметки «когда напоминала» и «когда проводила совещание» жили в
памяти цикла. Любой перезапуск — а деплой это перезапуск — обнулял
их, и напоминание приходило снова, независимо от того, сколько раз
уже приходило сегодня.

Файл маленький и переживает перезапуск; при поломке он игнорируется:
потерять отметку не страшно, а падать из-за неё на старте — страшно.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("anfinances_bot.state")

__all__ = ["BotState"]

_FIELDS = ("last_reminder_at", "last_meeting_at", "last_interaction_at")


class BotState:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._values: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text("utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            logger.warning("Состояние не читается, начинаю с чистого")
            return
        if isinstance(raw, dict):
            self._values = {
                key: str(value)
                for key, value in raw.items()
                if key in _FIELDS and isinstance(value, str)
            }

    def get(self, key: str) -> datetime | None:
        value = self._values.get(key)
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def set(self, key: str, moment: datetime | None = None) -> None:
        self._values[key] = (moment or datetime.now(UTC)).isoformat()
        self._save()

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Пишем через временный файл: прерванная запись не должна
            # оставить наполовину написанный json.
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._values), "utf-8")
            tmp.replace(self._path)
        except OSError:
            logger.warning("Не удалось сохранить состояние", exc_info=True)
