"""Распознавание голосовых через OpenAI Whisper.

Аудио уходит на распознавание, возвращается текст, файл удаляется
немедленно — и в успешной ветке, и в ветке с ошибкой. На сервере
голосовых не остаётся: это решение Р-8, и держится оно на finally,
а не на аккуратности вызывающего кода.
"""

import contextlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("anfinances_bot.speech")

__all__ = ["SpeechUnavailableError", "transcribe"]


class SpeechUnavailableError(RuntimeError):
    """Не удалось расшифровать голосовое."""


async def transcribe(openai_client: Any, audio_path: Path, model: str) -> str:
    """Расшифровать файл и удалить его, что бы ни случилось."""
    try:
        if not audio_path.exists():
            raise SpeechUnavailableError(f"Нет файла {audio_path}")
        try:
            with audio_path.open("rb") as handle:
                result = await openai_client.audio.transcriptions.create(
                    model=model,
                    file=handle,
                    language="ru",
                )
        except SpeechUnavailableError:
            raise
        except Exception as exc:
            logger.warning("Transcription failed", exc_info=True)
            raise SpeechUnavailableError(str(exc)) from exc

        text = str(result.text).strip()
        if not text:
            raise SpeechUnavailableError("Пустая расшифровка.")
        return text
    finally:
        with contextlib.suppress(OSError):
            audio_path.unlink(missing_ok=True)
