"""Отметка «бот на связи»: её ставит только удачный заход на сайт."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from anfinances_bot import health


class _StopLoopError(Exception):
    """Прервать бесконечный цикл после нужного числа проверок."""


class _Site:
    """Сайт, который пускает бота заданное число раз, потом нет."""

    def __init__(self, allowed: int = 99) -> None:
        self.allowed = allowed
        self.calls = 0

    async def me(self) -> object:
        self.calls += 1
        if self.calls > self.allowed:
            raise RuntimeError("Не удалось войти в anfinances")
        return object()


def _stop_after(monkeypatch: pytest.MonkeyPatch, ticks: int) -> None:
    seen = 0

    async def _sleep(_: float) -> None:
        nonlocal seen
        seen += 1
        if seen >= ticks:
            raise _StopLoopError

    monkeypatch.setattr(health.asyncio, "sleep", _sleep)


def test_health_path_lives_next_to_state(tmp_path: Path) -> None:
    assert health.health_path(str(tmp_path / "state.json")) == (
        tmp_path / "health.txt"
    )


def test_missing_mark_is_not_fresh(tmp_path: Path) -> None:
    assert health.is_fresh(tmp_path / "health.txt") is False


def test_broken_mark_is_not_fresh(tmp_path: Path) -> None:
    # Обрезанный или затёртый файл — то же самое, что его отсутствие.
    path = tmp_path / "health.txt"
    path.write_text("ни разу не дата", encoding="utf-8")

    assert health.is_fresh(path) is False


def test_fresh_mark_counts_and_old_one_does_not(tmp_path: Path) -> None:
    path = tmp_path / "health.txt"
    now = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)

    health.touch(path, now)

    assert health.is_fresh(path, now=now + timedelta(minutes=1)) is True
    assert health.is_fresh(path, now=now + timedelta(minutes=30)) is False


async def test_loop_marks_while_site_lets_bot_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "health.txt"
    _stop_after(monkeypatch, 2)
    site = _Site()

    with pytest.raises(_StopLoopError):
        await health.run_health_loop(site, path, interval=0)

    assert site.calls == 2
    assert health.is_fresh(path) is True


async def test_mark_goes_stale_when_site_stops_letting_bot_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Главный случай: пароль сменили, процесс жив, работать нечем."""
    path = tmp_path / "health.txt"
    old = datetime.now(UTC) - health.MAX_AGE - timedelta(minutes=1)
    health.touch(path, old)
    _stop_after(monkeypatch, 3)
    site = _Site(allowed=0)

    # Цикл не падает: сайт может лежать и из-за деплоя.
    with pytest.raises(_StopLoopError):
        await health.run_health_loop(site, path, interval=0)

    # Отметку никто не обновил — healthcheck увидит протухшую.
    assert site.calls == 3
    assert health.is_fresh(path) is False


def test_check_command_answers_by_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_STATE_PATH", str(tmp_path / "state.json"))

    assert health.main() == 1

    health.touch(tmp_path / "health.txt")

    assert health.main() == 0
