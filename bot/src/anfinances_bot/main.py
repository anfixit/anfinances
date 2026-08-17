"""Точка входа бота."""

import asyncio
import contextlib
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from anfinances_bot.agent.runner import AgentReply, AgentRunner
from anfinances_bot.agent.tools import ToolBox
from anfinances_bot.anfinances.client import AnfinancesClient
from anfinances_bot.anfinances.schemas import UserProfile
from anfinances_bot.config import get_bot_settings
from anfinances_bot.documents import (
    DocumentUnreadableError,
    read_image,
    read_statement,
)
from anfinances_bot.proactive_loop import run_proactive_loop
from anfinances_bot.speech import SpeechUnavailableError, transcribe
from anfinances_bot.telegram.access import AllowlistMiddleware
from anfinances_bot.telegram.handlers import (
    Session,
    handle_callback,
    handle_user_document,
    handle_user_photo,
    handle_user_text,
    handle_user_voice,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("anfinances_bot")


class Deps:
    """То, что нужно обработчику: агент плюс свежие справочники."""

    def __init__(
        self,
        client: AnfinancesClient,
        runner: AgentRunner,
        profile: UserProfile,
    ) -> None:
        self.client = client
        self._runner = runner
        self._profile = profile

    async def resolve(
        self,
        text: str,
        history: list[dict[str, Any]],
        images: list[tuple[str, str]] | None = None,
    ) -> AgentReply:
        # Счета и категории тянем каждый раз: она их правит на сайте,
        # а устаревший список тихо испортил бы разнесение операций.
        accounts = await self.client.accounts()
        categories = await self.client.categories()
        return await self._runner.run(
            text,
            accounts,
            categories,
            self._profile.timezone,
            history=history,
            images=images,
        )


async def _check_default_accounts(
    client: AnfinancesClient, defaults: dict[str, str]
) -> None:
    """Убедиться, что умолчания указывают на существующие счета.

    Имена, а не UUID: восстановление из бэкапа перегенерирует
    идентификаторы (ADR-020), и зашитый UUID указывал бы в никуда.
    Зато имя можно переименовать — поэтому проверяем на старте, а не
    на первой же трате.
    """
    accounts = await client.accounts()
    by_name = {a.name.casefold(): a for a in accounts}
    for code, name in defaults.items():
        account = by_name.get(name.casefold())
        if account is None:
            logger.error(
                "Счёт по умолчанию «%s» не найден. Доступные: %s",
                name,
                ", ".join(a.name for a in accounts),
            )
            sys.exit(1)
        if account.currency_code != code:
            logger.error(
                "Счёт «%s» в валюте %s, а назначен умолчанием для %s.",
                name,
                account.currency_code,
                code,
            )
            sys.exit(1)


async def main() -> None:
    settings = get_bot_settings()
    client = AnfinancesClient(settings)

    profile = await client.me()
    await _check_default_accounts(client, settings.bot_default_accounts)

    toolbox = ToolBox(
        client,
        default_accounts=settings.bot_default_accounts,
        timezone=profile.timezone,
    )
    runner = AgentRunner(
        AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()),
        toolbox,
    )
    deps = Deps(client, runner, profile)
    speech = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())

    # Разметку модели переводим в HTML сами; без parse_mode телеграм
    # покажет её как есть, звёздочками.
    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    allowlist = AllowlistMiddleware(settings.telegram_allowed_user_ids)
    dispatcher.message.middleware(allowlist)
    dispatcher.callback_query.middleware(allowlist)

    # Один чат — одна сессия. Бот личный, чатов больше одного не будет.
    sessions: dict[int, Session] = {}

    def _session(chat_id: int) -> Session:
        return sessions.setdefault(chat_id, Session())

    async def _download_and_transcribe(message: Message) -> str:
        """Скачать голосовое во временный файл и расшифровать."""
        if message.voice is None:
            raise SpeechUnavailableError("В сообщении нет голосового.")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "voice.ogg"
            await bot.download(message.voice, destination=path)
            return await transcribe(speech, path, settings.speech_model)

    @dispatcher.message(F.text)
    async def _on_text(message: Message) -> None:
        await handle_user_text(message, deps, _session(message.chat.id))

    async def _download_and_read(message: Message) -> tuple[str, str]:
        """Скачать присланный файл и прочитать его как текст."""
        document = message.document
        if document is None:
            raise DocumentUnreadableError("В сообщении нет файла.")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "statement"
            await bot.download(document, destination=path)
            return document.file_name or "выписка", read_statement(path)

    @dispatcher.message(F.document)
    async def _on_document(message: Message) -> None:
        # Скриншот часто присылают файлом, а не фото — тогда это
        # картинка, а не выписка, и читать её надо глазами модели.
        document = message.document
        mime = (document.mime_type or "") if document else ""
        session = _session(message.chat.id)
        if mime.startswith("image/"):
            await handle_user_photo(message, deps, session, _download_images)
            return
        await handle_user_document(message, deps, session, _download_and_read)

    async def _download_images(
        message: Message,
    ) -> list[tuple[str, str]]:
        """Скачать скриншот и подготовить его для модели."""
        # Телеграм отдаёт фото в нескольких размерах; последний —
        # самый крупный, на нём читаются суммы мелким шрифтом.
        source = message.photo[-1] if message.photo else message.document
        if source is None:
            raise DocumentUnreadableError("В сообщении нет картинки.")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shot"
            await bot.download(source, destination=path)
            name = message.document.file_name if message.document else ""
            return [read_image(path, name or "screenshot.jpg")]

    @dispatcher.message(F.photo)
    async def _on_photo(message: Message) -> None:
        await handle_user_photo(
            message, deps, _session(message.chat.id), _download_images
        )

    @dispatcher.message(F.voice)
    async def _on_voice(message: Message) -> None:
        await handle_user_voice(
            message,
            deps,
            _session(message.chat.id),
            _download_and_transcribe,
        )

    @dispatcher.callback_query()
    async def _on_callback(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return
        await handle_callback(
            callback, deps, _session(callback.message.chat.id)
        )

    proactive = asyncio.create_task(
        run_proactive_loop(bot, deps, settings, profile.timezone)
    )
    logger.info("Бот запущен, часовой пояс %s", profile.timezone)
    try:
        await dispatcher.start_polling(bot)
    finally:
        proactive.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await proactive
        await client.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
