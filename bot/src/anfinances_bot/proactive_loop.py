"""Фоновый цикл проактивных сообщений.

Решения «пора или нет» живут в ``proactive``; здесь только отправка
и расписание. Адресат — единственный разрешённый Telegram-ID: в
личных чатах идентификатор пользователя совпадает с чатом, поэтому
хранить соответствие не нужно.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from anfinances_bot.config import BotSettings
from anfinances_bot.proactive import (
    is_quiet,
    should_hold_meeting,
    should_remind,
)
from anfinances_bot.telegram.formatting import (
    split_message,
    to_telegram_html,
)

logger = logging.getLogger("anfinances_bot.proactive")

__all__ = ["run_proactive_loop"]

TICK_SECONDS = 900.0

REMINDER = (
    "Пару дней ничего не записывали. Если траты были — наговори их "
    "сейчас, пока помнишь."
)
MEETING_PROMPT = (
    "Проведи бюджетное совещание. Посмотри, как идёт текущий месяц: "
    "что уже потрачено против бюджета, где вылезли за лимит, покрыты "
    "ли траты доходом прошлого месяца, что с долгом по кредитам. "
    "Дальше предложи, как дожить остаток месяца. Совещание может "
    "выпадать на середину месяца — не притворяйся, что он только "
    "начался. Коротко, числами из инструментов."
)


class _Deps(Protocol):
    client: Any

    async def resolve(
        self, text: str, history: list[dict[str, Any]]
    ) -> Any: ...


async def run_proactive_loop(
    bot: Any,
    deps: _Deps,
    settings: BotSettings,
    timezone_name: str,
    state: Any,
) -> None:
    """Раз в 15 минут проверять, не пора ли написать первым.

    Отметки берутся из ``state``, а не из памяти цикла: перезапуск
    бота не должен выглядеть как новый повод напомнить.
    """
    chat_id = next(iter(settings.telegram_allowed_user_ids))
    zone = ZoneInfo(timezone_name)

    while True:
        try:
            now = datetime.now(UTC).astimezone(zone)
            if not is_quiet(now, settings.bot_quiet_hours):
                if should_hold_meeting(
                    now,
                    settings.bot_budget_meeting_day,
                    state.get("last_meeting_at"),
                ):
                    reply = await deps.resolve(MEETING_PROMPT, [])
                    for part in split_message(reply.text):
                        await bot.send_message(chat_id, to_telegram_html(part))
                    state.set("last_meeting_at", now)
                elif should_remind(
                    await _last_transaction_at(deps),
                    state.get("last_reminder_at"),
                    now,
                    state.get("last_interaction_at"),
                ):
                    await bot.send_message(chat_id, REMINDER)
                    state.set("last_reminder_at", now)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Сбой одной проверки не должен убивать цикл до перезапуска.
            logger.warning("Проактивный цикл споткнулся", exc_info=True)
        await asyncio.sleep(TICK_SECONDS)


async def _last_transaction_at(deps: _Deps) -> datetime | None:
    """Дата последней операции; None — если история пуста."""
    with contextlib.suppress(Exception):
        rows = await deps.client.request(
            "GET", "/transactions", params={"limit": 1}
        )
        if rows:
            return datetime.fromisoformat(rows[0]["date"])
    return None
