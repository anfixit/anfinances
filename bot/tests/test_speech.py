"""Распознавание речи: файл удаляется всегда."""

from pathlib import Path
from typing import Any

import pytest

from anfinances_bot.speech import SpeechUnavailableError, transcribe


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


class _Transcriptions:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> _Result:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return _Result("потратила триста рублей на кофе")


class _Audio:
    def __init__(self, error: Exception | None = None) -> None:
        self.transcriptions = _Transcriptions(error)


class _FakeOpenAI:
    def __init__(self, error: Exception | None = None) -> None:
        self.audio = _Audio(error)


def _audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "voice.ogg"
    path.write_bytes(b"fake-ogg")
    return path


async def test_returns_text_and_removes_file(tmp_path: Path) -> None:
    path = _audio_file(tmp_path)
    text = await transcribe(_FakeOpenAI(), path, "whisper-1")
    assert "кофе" in text
    assert not path.exists()


async def test_removes_file_on_failure(tmp_path: Path) -> None:
    """Голосовые не должны копиться на сервере даже после сбоя."""
    path = _audio_file(tmp_path)
    client = _FakeOpenAI(RuntimeError("недоступно"))
    with pytest.raises(SpeechUnavailableError):
        await transcribe(client, path, "whisper-1")
    assert not path.exists()


async def test_asks_russian(tmp_path: Path) -> None:
    path = _audio_file(tmp_path)
    client = _FakeOpenAI()
    await transcribe(client, path, "whisper-1")
    assert client.audio.transcriptions.kwargs["language"] == "ru"


async def test_empty_transcript_is_reported(tmp_path: Path) -> None:
    """Тишина в ответ на голосовое собьёт агента с толку."""
    path = _audio_file(tmp_path)
    client = _FakeOpenAI()
    client.audio.transcriptions = _Transcriptions()

    async def _empty(**kwargs: Any) -> _Result:
        return _Result("   ")

    client.audio.transcriptions.create = _empty  # type: ignore[method-assign]
    with pytest.raises(SpeechUnavailableError):
        await transcribe(client, path, "whisper-1")
    assert not path.exists()


async def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SpeechUnavailableError):
        await transcribe(_FakeOpenAI(), tmp_path / "нет.ogg", "whisper-1")
