"""Сборка системного промпта и точки кэширования."""

from anfinances_bot.agent.prompt import SYSTEM_PROMPT, build_system_blocks
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead

ACCOUNTS = [
    AccountRead(id="a-1", name="Альфа", currency_code="RUB"),
    AccountRead(id="a-3", name="Наличные сумы", currency_code="UZS"),
]
CATEGORIES = [
    CategoryRead(id="c-1", name="Еда", kind="expense"),
    CategoryRead(id="c-2", name="Кофейни", kind="expense", parent_id="c-1"),
    CategoryRead(id="c-3", name="Зарплата", kind="income"),
]


def test_last_block_is_cached() -> None:
    blocks = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in b for b in blocks[:-1])


def test_accounts_and_paths_present() -> None:
    blocks = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    text = "\n".join(str(b["text"]) for b in blocks)
    assert "Альфа (RUB)" in text
    assert "Наличные сумы (UZS)" in text
    assert "Еда → Кофейни" in text
    assert "Зарплата" in text


def test_timezone_present() -> None:
    blocks = build_system_blocks(ACCOUNTS, CATEGORIES, "Asia/Tashkent")
    text = "\n".join(str(b["text"]) for b in blocks)
    assert "Asia/Tashkent" in text


def test_prompt_states_transfer_rule() -> None:
    """Решение Р-9: обе суммы, курс не досчитывать."""
    lowered = SYSTEM_PROMPT.casefold()
    assert "обе" in lowered
    assert "курс" in lowered


def test_prompt_states_credit_split_rule() -> None:
    """Платёж по кредиту без разбивки разводит остаток с банком."""
    lowered = SYSTEM_PROMPT.casefold()
    assert "тело" in lowered
    assert "процент" in lowered


def test_prompt_carries_all_four_ynab_rules() -> None:
    """Без правил бот записывает траты, но бюджет не ведёт."""
    lowered = SYSTEM_PROMPT.casefold()
    assert "своя работа" in lowered
    assert "истинные расходы" in lowered
    assert "перенеси" in lowered
    assert "доход прошлого месяца" in lowered


def test_prompt_sends_daily_limit_to_the_tool() -> None:
    """Считать лимит в уме — верный способ соврать числом."""
    assert "get_daily_allowance" in SYSTEM_PROMPT


def test_prompt_allows_setting_up_the_site() -> None:
    assert "set_budget" in SYSTEM_PROMPT
    assert "не отправляй её на сайт" in SYSTEM_PROMPT.casefold()


def test_no_timestamp_in_cached_prefix() -> None:
    """Волатильное в кэшируемом префиксе обнуляло бы кэш."""
    first = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    second = build_system_blocks(ACCOUNTS, CATEGORIES, "Europe/Moscow")
    assert first == second


def test_category_order_is_stable() -> None:
    """Перестановка счетов с сервера не должна ломать кэш."""
    shuffled = [CATEGORIES[2], CATEGORIES[1], CATEGORIES[0]]
    assert build_system_blocks(
        ACCOUNTS, CATEGORIES, "Europe/Moscow"
    ) == build_system_blocks(ACCOUNTS, shuffled, "Europe/Moscow")
