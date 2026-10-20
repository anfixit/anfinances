"""Учёт расхода на модель за месяц и предупреждения о лимите."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from anfinances_bot.spend import SpendLog

OCT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
NOV = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_spend_adds_up_and_survives_a_restart(tmp_path: Path) -> None:
    """Деплой — это перезапуск; счёт за месяц от него не обнуляется."""
    path = tmp_path / "spend.json"
    log = SpendLog(path, limit=10)
    log.add(0.03, "claude-sonnet-5-5", now=OCT)
    log.add(0.40, "claude-opus-5-5", now=OCT)

    again = SpendLog(path, limit=10)
    assert again.current.dollars == pytest.approx(0.43)
    assert again.current.runs == 2
    report = again.report(now=OCT)
    assert "$0.43 из $10" in report
    assert "Opus" in report
    assert "Sonnet" in report


def test_warns_once_at_eighty_percent_and_once_at_the_limit(
    tmp_path: Path,
) -> None:
    log = SpendLog(tmp_path / "spend.json", limit=10)
    assert log.add(7.9, "claude-opus-5-5", now=OCT) is None
    first = log.add(0.2, "claude-sonnet-5-5", now=OCT)
    assert first is not None and "$8.10 из $10" in first
    assert log.add(0.5, "claude-sonnet-5-5", now=OCT) is None, "уже говорила"
    at_limit = log.add(1.5, "claude-opus-5-5", now=OCT)
    assert at_limit is not None and "лимит" in at_limit
    assert log.add(1.0, "claude-opus-5-5", now=OCT) is None


def test_new_month_starts_from_zero(tmp_path: Path) -> None:
    log = SpendLog(tmp_path / "spend.json", limit=10)
    log.add(9.0, "claude-opus-5-5", now=OCT)
    log.add(0.1, "claude-sonnet-5-5", now=NOV)
    assert log.current.month == "2026-11"
    assert log.current.dollars == 0.1
    assert log.current.warned == []
    assert "В ноябре" in log.report(now=NOV)


def test_first_month_is_marked_incomplete(tmp_path: Path) -> None:
    """Счёт начат 20-го — сравнивать с полным месяцем нельзя."""
    log = SpendLog(tmp_path / "spend.json", limit=10)
    log.add(0.1, "claude-sonnet-5-5", now=OCT)
    log.current.since = "2026-10-20"
    assert "с 20-го" in log.report(now=OCT)


def test_broken_file_does_not_stop_the_bot(tmp_path: Path) -> None:
    path = tmp_path / "spend.json"
    path.write_text("{не json", "utf-8")
    log = SpendLog(path, limit=10)
    assert log.current.dollars == 0
    log.add(0.1, "claude-sonnet-5-5", now=OCT)
    assert SpendLog(path, limit=10).current.dollars == 0.1
