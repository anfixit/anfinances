"""Обработчики сообщений.

Ни один сбой не должен приводить к тихой потере операции: если
записать не удалось, бот говорит об этом прямо, а не делает вид,
что всё прошло.

Разговор помнит несколько последних ходов — иначе «а на сбере?»
не к чему привязать, а кнопки под карточкой некуда возвращать.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from anfinances_bot.agent.runner import AgentReply, AgentUnavailableError
from anfinances_bot.anfinances.client import (
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.documents import DocumentUnreadableError
from anfinances_bot.speech import SpeechUnavailableError
from anfinances_bot.telegram.formatting import (
    split_message,
    to_telegram_html,
)
from anfinances_bot.telegram.keyboards import (
    account_choice,
    parse_callback,
    transaction_card,
)

logger = logging.getLogger("anfinances_bot.handlers")

__all__ = [
    "Session",
    "handle_callback",
    "handle_user_document",
    "handle_user_text",
    "handle_user_voice",
]

SITE_DOWN = (
    "Не смогла записать: anfinances сейчас недоступен. "
    "Повтори через пару минут — я ничего не потеряла и не записала."
)
MODEL_DOWN = (
    "Не смогла разобрать фразу: модель недоступна. "
    "Запиши, пожалуйста, через сайт."
)
SPEECH_DOWN = "Не смогла разобрать голосовое. Напиши, пожалуйста, текстом."
FIX_PROMPT = "Что исправить? Напиши, например: «это был транспорт»."
DOC_UNREADABLE = "Не смогла прочитать файл."


@dataclass
class Session:
    """Память одного чата: последние ходы и незакрытые уточнения."""

    MAX_HISTORY = 12

    history: list[dict[str, Any]] = field(default_factory=list)
    pending_accounts: list[AccountRead] = field(default_factory=list)
    pending_fix_id: str | None = None

    def remember(self, question: str, answer: str) -> None:
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        # Держим окно коротким: длинная история дороже, чем полезнее.
        del self.history[: -self.MAX_HISTORY]


class _Deps(Protocol):
    async def resolve(
        self, text: str, history: list[dict[str, Any]]
    ) -> AgentReply: ...


async def handle_user_text(
    message: Any, deps: _Deps, session: Session
) -> None:
    prompt = message.text
    if session.pending_fix_id is not None:
        prompt = f"Исправь операцию с id {session.pending_fix_id}: {prompt}"
        session.pending_fix_id = None
    await _run(message, deps, session, prompt)


async def handle_callback(
    callback: Any, deps: _Deps, session: Session
) -> None:
    """Обработать нажатие кнопки под сообщением бота."""
    try:
        action, value = parse_callback(callback.data or "")
    except ValueError:
        logger.warning("Неразбираемый callback: %r", callback.data)
        await callback.answer()
        return

    await callback.answer()

    if action == "fix":
        session.pending_fix_id = value
        await _say(callback.message, FIX_PROMPT)
        return

    if action == "del":
        await _run(
            callback.message,
            deps,
            session,
            f"Удали операцию с id {value}.",
        )
        return

    if action == "acc":
        chosen = next(
            (a for a in session.pending_accounts if a.id == value), None
        )
        session.pending_accounts = []
        if chosen is None:
            await _say(
                callback.message,
                "Не помню, о какой операции речь. Повтори, пожалуйста.",
            )
            return
        await _run(
            callback.message,
            deps,
            session,
            f"Счёт: {chosen.name}. Запиши операцию, о которой шла речь.",
        )
        return

    logger.warning("Неизвестное действие кнопки: %s", action)


async def handle_user_voice(
    message: Any, deps: _Deps, session: Session, transcriber: Any
) -> None:
    """Расшифровать голосовое и обработать как текст."""
    try:
        text = await transcriber(message)
    except SpeechUnavailableError:
        logger.warning("Расшифровка не удалась", exc_info=True)
        await _say(message, SPEECH_DOWN)
        return

    # Показываем расшифровку: Whisper ошибается, и это надо видеть.
    await _say(message, f"Услышала: {text}")
    message.text = text
    await handle_user_text(message, deps, session)


async def handle_user_document(
    message: Any, deps: _Deps, session: Session, reader: Any
) -> None:
    """Принять файл выписки и отдать его содержимое агенту."""
    try:
        name, text = await reader(message)
    except DocumentUnreadableError as exc:
        logger.warning("Файл не прочитан", exc_info=True)
        await _say(message, f"{DOC_UNREADABLE} {exc}")
        return

    await _say(message, f"Читаю {name}…")
    await _run(
        message,
        deps,
        session,
        (
            f"Это банковская выписка из файла {name}. Разбери её: "
            "определи, где дата, сумма и назначение платежа, отдели "
            "расходы от доходов, подбери категории из существующего "
            "дерева и занеси всё разом через import_statement. "
            "Если непонятно, по какому счёту выписка, — спроси.\n\n"
            f"{text}"
        ),
        remember_as=f"[прислала банковскую выписку {name}]",
    )


async def _run(
    message: Any,
    deps: _Deps,
    session: Session,
    prompt: str,
    remember_as: str | None = None,
) -> None:
    """Прогнать фразу через агента и ответить нужным способом.

    ``remember_as`` кладётся в историю вместо ``prompt``: выписка
    на десятки тысяч знаков иначе уезжала бы в модель на каждом
    следующем сообщении.
    """
    try:
        reply = await deps.resolve(prompt, session.history)
    except AnfinancesUnavailableError:
        logger.warning("anfinances недоступен", exc_info=True)
        await _say(message, SITE_DOWN)
        return
    except AgentUnavailableError:
        logger.warning("Модель недоступна", exc_info=True)
        await _say(message, MODEL_DOWN)
        return
    except AnfinancesError as exc:
        await _say(message, f"Не получилось: {exc}")
        return

    session.remember(remember_as or prompt, reply.text)

    if reply.created_transaction_id is not None:
        await _say(
            message,
            reply.text,
            transaction_card(reply.created_transaction_id),
        )
        return

    if reply.pending_accounts:
        session.pending_accounts = list(reply.pending_accounts)
        await _say(
            message,
            reply.text or "С какого счёта?",
            account_choice(reply.pending_accounts),
        )
        return

    await _say(message, reply.text or "Не поняла, повтори иначе.")


async def _say(message: Any, text: str, markup: Any = None) -> None:
    """Отправить ответ модели: разметка в HTML, длинное — по кускам.

    Кнопки вешаются на последний кусок: под серединой ответа они
    выглядят как обрыв.
    """
    parts = split_message(text)
    for index, part in enumerate(parts):
        is_last = index == len(parts) - 1
        await message.answer(
            to_telegram_html(part),
            reply_markup=markup if is_last else None,
        )
