"""Пять правил разрешения счёта (решение Р-6).

Цена ошибки со счётом выше, чем с категорией: неправильная категория
портит отчёт и это заметно, неправильный счёт разводит баланс с
реальностью и обнаруживается через неделю.

Набор счетов взят настоящий: пять начинаются с «Альфа», сумовых
три, долларовых два. Именно на таком наборе ломаются наивные правила.
"""

from decimal import Decimal

from anfinances_bot.anfinances.schemas import AccountRead
from anfinances_bot.resolve.accounts import resolve_account


def _acc(id_: str, name: str, currency: str) -> AccountRead:
    return AccountRead(
        id=id_,
        name=name,
        currency_code=currency,
        current_balance=Decimal("0"),
    )


ALFA = _acc("a-1", "Альфа", "RUB")
ALFA_ONLY = _acc("a-2", "Альфа Only", "RUB")
ALFA_BUSINESS = _acc("a-3", "Альфа Бизнес", "RUB")
ALFA_SAVINGS = _acc("a-4", "Альфа-счет на ежедневный остаток", "RUB")
SBER = _acc("a-6", "Сбер", "RUB")
RUB_CASH = _acc("a-8", "RUB Наличка", "RUB")

UZCARD = _acc("u-1", "Uzcard Капитал", "UZS")
HUMO = _acc("u-2", "Humo Капитал", "UZS")
UZS_CASH = _acc("u-3", "UZS Наличка", "UZS")

VISA = _acc("d-1", "Visa Капитал", "USD")
USD_CASH = _acc("d-2", "USD Наличка", "USD")

ALL = [
    ALFA,
    ALFA_ONLY,
    ALFA_BUSINESS,
    ALFA_SAVINGS,
    SBER,
    RUB_CASH,
    UZCARD,
    HUMO,
    UZS_CASH,
    VISA,
    USD_CASH,
]

DEFAULTS = {
    "RUB": "Альфа",
    "UZS": "Uzcard Капитал",
    "USD": "Visa Капитал",
}


def _resolve(
    *,
    named: str | None = None,
    currency: str | None = None,
    history: str | None = None,
    accounts: list[AccountRead] | None = None,
) -> object:
    return resolve_account(
        ALL if accounts is None else accounts,
        named=named,
        currency_code=currency,
        history_account_id=history,
        default_names=DEFAULTS,
    )


def test_step1_unique_substring_wins() -> None:
    assert _resolve(named="сбер", currency="RUB").account == SBER  # type: ignore[attr-defined]


def test_step1_exact_name_beats_ambiguous_substring() -> None:
    """«Альфа» — точное имя, хотя подстрока подходит пяти счетам."""
    assert _resolve(named="Альфа", currency="RUB").account == ALFA  # type: ignore[attr-defined]


def test_step1_exact_match_is_case_insensitive() -> None:
    assert _resolve(named="АЛЬФА", currency="RUB").account == ALFA  # type: ignore[attr-defined]


def test_step1_ambiguous_substring_falls_through() -> None:
    """«Капитал» подходит трём счетам — угадывать нельзя."""
    result = _resolve(named="Капитал", currency="UZS")
    # Точного имени нет, подстрока неоднозначна → работает умолчание.
    assert result.account == UZCARD  # type: ignore[attr-defined]


def test_step1_named_wins_over_default() -> None:
    assert _resolve(named="Humo", currency="UZS").account == HUMO  # type: ignore[attr-defined]


def test_step2_single_account_in_currency() -> None:
    only_one = [ALFA, VISA]
    result = _resolve(currency="USD", accounts=only_one)
    assert result.account == VISA  # type: ignore[attr-defined]


def test_step3_history_decides() -> None:
    assert _resolve(currency="RUB", history="a-6").account == SBER  # type: ignore[attr-defined]


def test_step4_default_per_currency_rub() -> None:
    assert _resolve(currency="RUB").account == ALFA  # type: ignore[attr-defined]


def test_step4_default_per_currency_uzs() -> None:
    """Раньше сумовая трата упиралась в кнопки — теперь есть умолчание."""
    assert _resolve(currency="UZS").account == UZCARD  # type: ignore[attr-defined]


def test_step4_default_per_currency_usd() -> None:
    assert _resolve(currency="USD").account == VISA  # type: ignore[attr-defined]


def test_step4_does_not_match_alfa_prefixes() -> None:
    """«Альфа» не должна цеплять «Альфа Бизнес» или накопительный."""
    result = _resolve(currency="RUB")
    assert result.account == ALFA  # type: ignore[attr-defined]
    assert result.account != ALFA_BUSINESS  # type: ignore[attr-defined]


def test_step5_buttons_when_currency_has_no_default() -> None:
    eur_a = _acc("e-1", "EUR A", "EUR")
    eur_b = _acc("e-2", "EUR B", "EUR")
    result = _resolve(currency="EUR", accounts=[*ALL, eur_a, eur_b])
    assert result.account is None  # type: ignore[attr-defined]
    assert result.candidates == [eur_a, eur_b]  # type: ignore[attr-defined]


def test_history_ignored_if_currency_mismatches() -> None:
    """Подсказка из истории не должна ломать валюту операции."""
    assert _resolve(currency="UZS", history="a-1").account == UZCARD  # type: ignore[attr-defined]


def test_unknown_named_account_falls_through() -> None:
    assert _resolve(named="Райффайзен", currency="RUB").account == ALFA  # type: ignore[attr-defined]


def test_empty_account_list_gives_no_candidates() -> None:
    result = _resolve(currency="RUB", accounts=[])
    assert result.account is None  # type: ignore[attr-defined]
    assert result.candidates == []  # type: ignore[attr-defined]
