"""Фоновое обновление курсов переживает сбои провайдера."""

import asyncio

import pytest

from app.domains.currencies.scheduler import refresh_rates_periodically


class _Recorder:
    """Считает вызовы; на первом бросает, чтобы проверить живучесть."""

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self._fail_first = fail_first

    async def __call__(self) -> None:
        self.calls += 1
        if self._fail_first and self.calls == 1:
            raise RuntimeError("провайдер недоступен")


async def test_refreshes_repeatedly() -> None:
    recorder = _Recorder()
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert recorder.calls >= 2


async def test_survives_provider_failure() -> None:
    recorder = _Recorder(fail_first=True)
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Первый вызов упал, но цикл продолжился.
    assert recorder.calls >= 2


async def test_cancellation_is_prompt() -> None:
    recorder = _Recorder()
    task = asyncio.create_task(
        refresh_rates_periodically(recorder, interval_seconds=3600)
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.done()
