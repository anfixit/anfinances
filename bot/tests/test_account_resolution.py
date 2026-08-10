"""Пять правил разрешения счёта (решение Р-6).

Цена ошибки со счётом выше, чем с категорией: неправильная категория
портит отчёт и это заметно, неправильный счёт разводит баланс с
реальностью и обнаруживается через неделю.
"""

from decimal import Decimal

from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.resolve.accounts import resolve_account

ALFA = AccountRead(
    id="a-1",
    name="Альфа",
    currency_code="RUB",
    current_balance=Decimal("100"),
)
SBER = AccountRead(
    id="a-2",
    name="Сбер карта",
    currency_code="RUB",
    current_balance=Decimal("200"),
)
CASH_UZS = AccountRead(
    id="a-3",
    name="Наличные сумы",
    currency_code="UZS",
    current_balance=Decimal("500000"),
)
ALL = [ALFA, SBER, CASH_UZS]

EUR_A = AccountRead(id="e-1", name="EUR A", currency_code="EUR")
EUR_B = AccountRead(id="e-2", name="EUR B", currency_code="EUR")


def test_step1_named_account_wins() -> None:
    result = resolve_account(
        ALL,
        named="сбер",
        currency_code="RUB",
        history_account_id="a-1",
        default_name="Альфа",
    )
    assert result.account == SBER


def test_step1_matching_is_case_insensitive() -> None:
    result = resolve_account(
        ALL,
        named="АЛЬФА",
        currency_code=None,
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_step2_single_account_in_currency() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="UZS",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == CASH_UZS


def test_step3_history_decides() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="RUB",
        history_account_id="a-2",
        default_name="Альфа",
    )
    assert result.account == SBER


def test_step4_default_account() -> None:
    result = resolve_account(
        ALL,
        named=None,
        currency_code="RUB",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_step5_buttons_when_nothing_helps() -> None:
    result = resolve_account(
        [*ALL, EUR_A, EUR_B],
        named=None,
        currency_code="EUR",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account is None
    assert result.candidates == [EUR_A, EUR_B]


def test_history_ignored_if_currency_mismatches() -> None:
    """Подсказка из истории не должна ломать валюту операции."""
    result = resolve_account(
        ALL,
        named=None,
        currency_code="UZS",
        history_account_id="a-1",
        default_name="Альфа",
    )
    assert result.account == CASH_UZS


def test_unknown_default_name_falls_to_buttons() -> None:
    result = resolve_account(
        [EUR_A, EUR_B],
        named=None,
        currency_code="EUR",
        history_account_id=None,
        default_name="Нет такого счёта",
    )
    assert result.account is None
    assert result.candidates == [EUR_A, EUR_B]


def test_named_account_not_found_does_not_win() -> None:
    """Названного счёта нет — идём дальше по правилам, а не падаем."""
    result = resolve_account(
        ALL,
        named="Тинькофф",
        currency_code="RUB",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_default_matches_whole_name_not_substring() -> None:
    """«Альфа» не должна цеплять «Альфа копилка» вместо «Альфа»."""
    piggy = AccountRead(id="a-9", name="Альфа копилка", currency_code="RUB")
    result = resolve_account(
        [piggy, ALFA],
        named=None,
        currency_code="RUB",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account == ALFA


def test_empty_account_list_gives_no_candidates() -> None:
    result = resolve_account(
        [],
        named=None,
        currency_code="RUB",
        history_account_id=None,
        default_name="Альфа",
    )
    assert result.account is None
    assert result.candidates == []
