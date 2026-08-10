"""Инлайн-клавиатуры бота."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from anfinances_bot.anfinances.schemas import AccountRead

__all__ = ["account_choice", "parse_callback", "transaction_card"]


def transaction_card(transaction_id: str) -> InlineKeyboardMarkup:
    """Кнопки под карточкой созданной операции."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Исправить",
                    callback_data=f"fix:{transaction_id}",
                ),
                InlineKeyboardButton(
                    text="Удалить",
                    callback_data=f"del:{transaction_id}",
                ),
            ]
        ]
    )


def account_choice(accounts: list[AccountRead]) -> InlineKeyboardMarkup:
    """Ряд кнопок со счетами — шаг 5 разрешения счёта.

    Валюту дописываем, только если одноимённые счета иначе не
    различить: лишний хвост у каждой кнопки читается хуже.
    """
    names = [a.name for a in accounts]
    ambiguous = {name for name in names if names.count(name) > 1}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        f"{a.name} ({a.currency_code})"
                        if a.name in ambiguous
                        else a.name
                    ),
                    callback_data=f"acc:{a.id}",
                )
            ]
            for a in accounts
        ]
    )


def parse_callback(data: str) -> tuple[str, str]:
    """Разобрать ``действие:идентификатор``."""
    action, separator, value = data.partition(":")
    if not separator or not action or not value:
        raise ValueError(f"Неразбираемый callback_data: {data!r}")
    return action, value
