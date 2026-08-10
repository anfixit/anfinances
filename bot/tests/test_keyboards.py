"""Клавиатуры: карточка операции и выбор счёта."""

import pytest

from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.telegram.keyboards import (
    account_choice,
    parse_callback,
    transaction_card,
)

ACCOUNTS = [
    AccountRead(id="a-1", name="Альфа", currency_code="RUB"),
    AccountRead(id="a-2", name="Сбер", currency_code="RUB"),
]


def test_card_has_fix_and_delete() -> None:
    markup = transaction_card("tx-1")
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["fix:tx-1", "del:tx-1"]


def test_account_choice_lists_all() -> None:
    markup = account_choice(ACCOUNTS)
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["acc:a-1", "acc:a-2"]


def test_account_choice_shows_currency_when_they_differ() -> None:
    """Два «Наличных» без валюты не различить."""
    accounts = [
        AccountRead(id="a-1", name="Наличка", currency_code="RUB"),
        AccountRead(id="a-2", name="Наличка", currency_code="UZS"),
    ]
    markup = account_choice(accounts)
    labels = [b.text for row in markup.inline_keyboard for b in row]
    assert labels == ["Наличка (RUB)", "Наличка (UZS)"]


def test_parse_callback_splits_action_and_id() -> None:
    assert parse_callback("fix:tx-1") == ("fix", "tx-1")
    assert parse_callback("acc:a-9") == ("acc", "a-9")


def test_parse_callback_keeps_colons_in_value() -> None:
    assert parse_callback("del:a:b") == ("del", "a:b")


@pytest.mark.parametrize("data", ["мусор", "fix:", ":tx-1", ""])
def test_parse_callback_rejects_garbage(data: str) -> None:
    with pytest.raises(ValueError):
        parse_callback(data)
