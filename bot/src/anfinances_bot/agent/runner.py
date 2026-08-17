"""Агентный цикл поверх tool_runner.

Один агент с инструментами вместо режимов: он сам решает, что
вызвать. Фраза «потратила 300 на кофе, а сколько осталось»
обрабатывается за один заход — запись, чтение, связный ответ.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from anfinances_bot.agent.prompt import build_system_blocks
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead

logger = logging.getLogger("anfinances_bot.agent")

__all__ = ["AgentReply", "AgentRunner", "AgentUnavailableError"]

MODEL = "claude-opus-5"
MAX_TOKENS = 8000
# Одна фраза редко требует больше: запись, пара чтений, ответ.
MAX_ITERATIONS = 12

_WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


class AgentUnavailableError(RuntimeError):
    """Модель недоступна или ответила ошибкой."""


@dataclass
class AgentReply:
    text: str
    created_transaction_id: str | None = None
    pending_accounts: list[AccountRead] = field(default_factory=list)


class _ToolBox(Protocol):
    tools: list[Any]
    last_created_id: str | None
    pending_accounts: list[AccountRead]


class AgentRunner:
    def __init__(self, anthropic: Any, toolbox: _ToolBox) -> None:
        self._anthropic = anthropic
        self._toolbox = toolbox

    async def run(
        self,
        text: str,
        accounts: list[AccountRead],
        categories: list[CategoryRead],
        timezone_name: str,
        history: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
        images: list[tuple[str, str]] | None = None,
    ) -> AgentReply:
        """Прогнать фразу через агента.

        ``images`` — пары «media_type, base64». Скриншот чека или
        выписки читает сама модель: разбирать картинку кодом здесь
        нечем, а разложить её по колонкам она умеет.
        """
        # Отметки прошлого запуска обнуляем: иначе карточка операции
        # прилипнет к ответу, который ничего не записывал.
        self._toolbox.last_created_id = None
        self._toolbox.pending_accounts = []

        system = build_system_blocks(accounts, categories, timezone_name)
        messages: list[dict[str, Any]] = list(history or [])
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            }
            for media_type, data in images or []
        ]
        content.append(
            {
                "type": "text",
                "text": f"{_now_line(timezone_name, now)}\n\n{text}",
            }
        )
        messages.append({"role": "user", "content": content})

        try:
            runner = self._anthropic.beta.messages.tool_runner(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                max_iterations=MAX_ITERATIONS,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=system,
                tools=self._toolbox.tools,
                messages=messages,
            )
            final = await runner.until_done()
        except Exception as exc:
            logger.error("Agent run failed", exc_info=True)
            raise AgentUnavailableError(str(exc)) from exc

        return AgentReply(
            text=_text_of(final),
            created_transaction_id=self._toolbox.last_created_id,
            pending_accounts=list(self._toolbox.pending_accounts),
        )


def _now_line(timezone_name: str, now: datetime | None) -> str:
    """Текущий момент — в сообщение, а не в кэшируемый префикс.

    Без сегодняшней даты «вчера» и «в пятницу» не разрешить, но в
    префиксе она обнуляла бы кэш каждые сутки.
    """
    moment = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone_name))
    weekday = _WEEKDAYS[moment.weekday()]
    return f"Сейчас: {moment.strftime('%Y-%m-%d %H:%M')}, {weekday}."


def _text_of(message: Any) -> str:
    """Собрать текст финального сообщения без блоков размышлений."""
    parts = [
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    ]
    return "\n".join(p for p in parts if p).strip()
