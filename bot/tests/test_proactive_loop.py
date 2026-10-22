"""Фоновый цикл: совещание не теряется и не оплачивается дважды."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from anfinances_bot import proactive_loop
from anfinances_bot.state import BotState


class _StopLoopError(Exception):
    """Прервать бесконечный цикл после нужного числа проверок."""


class _Deps:
    def __init__(self) -> None:
        self.client = SimpleNamespace()
        self.runs = 0

    async def resolve(self, text: str, history: list[Any]) -> Any:
        self.runs += 1
        return SimpleNamespace(text=f"Совещание №{self.runs}")


class _FlakyBot:
    """Первая отправка падает — как при недоступном телеграме."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.failures_left = 1

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.failures_left:
            self.failures_left -= 1
            raise RuntimeError("telegram недоступен")
        self.sent.append(text)


async def test_unsent_meeting_is_resent_not_regenerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = 0

    async def _sleep(_: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 2:
            raise _StopLoopError

    monkeypatch.setattr(proactive_loop.asyncio, "sleep", _sleep)
    settings = SimpleNamespace(
        telegram_allowed_user_ids=frozenset({42}),
        bot_quiet_hours=(0, 0),
        bot_budget_meeting_day=1,
        bot_ai_enabled=True,
    )
    deps = _Deps()
    bot = _FlakyBot()
    state = BotState(tmp_path / "state.json")

    with pytest.raises(_StopLoopError):
        await proactive_loop.run_proactive_loop(
            bot,
            deps,
            settings,  # type: ignore[arg-type]
            "UTC",
            state,
        )

    assert deps.runs == 1, "модель гоняли один раз"
    assert bot.sent == ["Совещание №1"]
    held = state.get("last_meeting_at")
    assert held is not None
    assert (held.year, held.month) == (
        datetime.now(UTC).year,
        datetime.now(UTC).month,
    )


async def test_no_meeting_without_ai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Совещание пишет модель: без ИИ его нет, и модель не зовётся."""
    ticks = 0

    async def _sleep(_: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 1:
            raise _StopLoopError

    monkeypatch.setattr(proactive_loop.asyncio, "sleep", _sleep)
    settings = SimpleNamespace(
        telegram_allowed_user_ids=frozenset({42}),
        bot_quiet_hours=(0, 0),
        bot_budget_meeting_day=1,
        bot_ai_enabled=False,
    )
    deps = _Deps()
    bot = _FlakyBot()
    bot.failures_left = 0

    async def _no_transactions(*_: Any, **__: Any) -> list[Any]:
        return [{"date": datetime.now(UTC).isoformat()}]

    deps.client = SimpleNamespace(request=_no_transactions)
    with pytest.raises(_StopLoopError):
        await proactive_loop.run_proactive_loop(
            bot,
            deps,
            settings,  # type: ignore[arg-type]
            "UTC",
            BotState(tmp_path / "state.json"),
        )
    assert deps.runs == 0
    assert bot.sent == []
