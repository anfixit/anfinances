"""Сколько бот потратил на модель за месяц.

Бюджет на бота — десять долларов в месяц, а настоящий счёт виден
только в консоли Anthropic, куда никто не заглядывает, пока не придёт
письмо о списании. Здесь — оценка по токенам каждого ответа: та же,
что пишется в лог, только сложенная за месяц и сохранённая на диск,
чтобы деплой её не обнулял.

Оценка, а не счёт: в неё не попадают упавшие прогоны и расшифровка
голосовых (это OpenAI). Для «подходим ли к лимиту» её хватает.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("anfinances_bot.spend")

__all__ = ["MonthSpend", "SpendLog", "spend_report"]

# Доли лимита, на которых бот сам предупреждает — по разу в месяц.
_WARN_AT = (0.8, 1.0)

_MONTHS = (
    "январе",
    "феврале",
    "марте",
    "апреле",
    "мае",
    "июне",
    "июле",
    "августе",
    "сентябре",
    "октябре",
    "ноябре",
    "декабре",
)


@dataclass
class MonthSpend:
    month: str
    dollars: float = 0.0
    runs: int = 0
    by_model: dict[str, float] = field(default_factory=dict)
    warned: list[float] = field(default_factory=list)
    # С какого дня ведётся счёт: в первый месяц он неполный.
    since: str = ""


class SpendLog:
    def __init__(self, path: Path, limit: float) -> None:
        self._path = path
        self.limit = limit
        self.current = self._load()

    def add(
        self, dollars: float, model: str, now: datetime | None = None
    ) -> str | None:
        """Прибавить ответ к месяцу; вернуть предупреждение, если пора."""
        moment = now or datetime.now(UTC)
        self._roll(moment)
        month = self.current
        month.dollars += dollars
        month.runs += 1
        month.by_model[model] = month.by_model.get(model, 0.0) + dollars

        notice = None
        for share in _WARN_AT:
            if share in month.warned or month.dollars < self.limit * share:
                continue
            month.warned.append(share)
            notice = _warning(month, self.limit, share)
        self._save()
        return notice

    def report(self, now: datetime | None = None) -> str:
        self._roll(now or datetime.now(UTC))
        return spend_report(self.current, self.limit)

    def _roll(self, moment: datetime) -> None:
        """Новый месяц — новый счёт."""
        key = moment.strftime("%Y-%m")
        if self.current.month != key:
            self.current = MonthSpend(
                month=key, since=moment.date().isoformat()
            )

    def _load(self) -> MonthSpend:
        now = datetime.now(UTC)
        fresh = MonthSpend(
            month=now.strftime("%Y-%m"), since=now.date().isoformat()
        )
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            return MonthSpend(
                month=str(raw["month"]),
                dollars=float(raw["dollars"]),
                runs=int(raw["runs"]),
                by_model={
                    str(k): float(v) for k, v in raw["by_model"].items()
                },
                warned=[float(x) for x in raw["warned"]],
                since=str(raw.get("since", "")),
            )
        except FileNotFoundError:
            return fresh
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # Потерять оценку не страшно, падать из-за неё — страшно.
            logger.warning("Учёт расхода не читается, начинаю с нуля")
            return fresh

    def _save(self) -> None:
        month = self.current
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "month": month.month,
                        "dollars": month.dollars,
                        "runs": month.runs,
                        "by_model": month.by_model,
                        "warned": month.warned,
                        "since": month.since,
                    }
                ),
                "utf-8",
            )
            tmp.replace(self._path)
        except OSError:
            logger.warning("Не удалось сохранить расход", exc_info=True)


def spend_report(month: MonthSpend, limit: float) -> str:
    name = _MONTHS[int(month.month[5:]) - 1]
    lines = [
        f"В {name} бот потратил примерно ${month.dollars:.2f} "
        f"из ${limit:.0f} — ответов: {month.runs}."
    ]
    for model, dollars in sorted(
        month.by_model.items(), key=lambda item: -item[1]
    ):
        lines.append(f"• {_model_name(model)}: ${dollars:.2f}")
    if month.since and not month.since.endswith("-01"):
        day = month.since[8:].lstrip("0")
        lines.append(f"Счёт ведётся с {day}-го — месяц неполный.")
    lines.append("Это оценка по токенам; точный счёт — в Anthropic Console.")
    return "\n".join(lines)


def _warning(month: MonthSpend, limit: float, share: float) -> str:
    if share >= 1.0:
        return (
            f"Расход на бота в этом месяце дошёл до ${month.dollars:.2f} — "
            f"это лимит ${limit:.0f}. Если в консоли Anthropic стоит "
            "ограничение, скоро я перестану отвечать до следующего месяца."
        )
    return (
        f"Расход на бота в этом месяце — ${month.dollars:.2f} из "
        f"${limit:.0f}. Подробности — /расход."
    )


def _model_name(model: str) -> str:
    if "sonnet" in model:
        return "Sonnet (простые фразы)"
    if "opus" in model:
        return "Opus (выписки и документы)"
    return model
