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

__all__ = [
    "AgentReply",
    "AgentRunner",
    "AgentUnavailableError",
]

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
    """Модель недоступна или ответила ошибкой.

    ``reason`` — короткий текст для пользователя. Без него все
    отказы выглядели одинаково, и «кончились деньги на API»
    невозможно было отличить от «сервис перегружен, повтори».
    """

    def __init__(self, message: str, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or MODEL_DOWN_DEFAULT


MODEL_DOWN_DEFAULT = (
    "Не смогла разобрать фразу: модель недоступна. "
    "Запиши, пожалуйста, через сайт."
)
BILLING = (
    "На счету Anthropic API кончились деньги — без них я не могу "
    "ничего разобрать. Пополни баланс в Plans & Billing, и я продолжу."
)
RATE_LIMIT = "Слишком много запросов подряд. Подожди минуту и повтори."
OVERLOADED = (
    "Модель сейчас перегружена. Повтори через пару минут — "
    "я ничего не потеряла."
)


def _reason_for(exc: Exception) -> str:
    """Перевести ошибку API в то, что человеку делать дальше."""
    text = str(exc).casefold()
    if "credit balance" in text or "billing" in text:
        return BILLING
    if "rate limit" in text or "429" in text:
        return RATE_LIMIT
    if "overloaded" in text or "529" in text:
        return OVERLOADED
    if "authentication" in text or "401" in text:
        return (
            "Ключ Anthropic API не принят. Проверь ANTHROPIC_API_KEY "
            "в секретах."
        )
    return MODEL_DOWN_DEFAULT


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
        pdfs: list[str] | None = None,
    ) -> AgentReply:
        """Прогнать фразу через агента.

        ``images`` — пары «media_type, base64», ``pdfs`` — base64
        страниц. Скриншот и PDF читает сама модель: банковская
        выписка свёрстана таблицей, и вытащенный кодом текст теряет
        привязку числа к строке.
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
        content.extend(
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": data,
                },
            }
            for data in pdfs or []
        )
        question: dict[str, Any] = {
            "type": "text",
            "text": f"{_now_line(timezone_name, now)}\n\n{text}",
        }
        if images or pdfs:
            # Агент ходит в модель несколько раз на одну фразу, и
            # каждый раз пересылает всю переписку — вместе с выпиской
            # на сотню тысяч токенов. С кэшем повторные шаги читают
            # её вдесятеро дешевле. Пяти минут хватает: шаги идут
            # секунда за секундой.
            question["cache_control"] = {"type": "ephemeral", "ttl": "5m"}
        content.append(question)
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
            raise AgentUnavailableError(str(exc), _reason_for(exc)) from exc

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
