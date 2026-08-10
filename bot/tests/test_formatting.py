"""Markdown модели → HTML телеграма."""

from anfinances_bot.telegram.formatting import (
    MAX_MESSAGE,
    split_message,
    to_telegram_html,
)


def test_bold_becomes_tag() -> None:
    assert to_telegram_html("**Операции:** траты") == (
        "<b>Операции:</b> траты"
    )


def test_italic_forms() -> None:
    assert to_telegram_html("*тихо* и _тоже_") == "<i>тихо</i> и <i>тоже</i>"


def test_bold_wins_over_italic() -> None:
    """`**жирный**` не должен разобраться как два курсива."""
    assert to_telegram_html("**точно**") == "<b>точно</b>"


def test_inline_code() -> None:
    assert to_telegram_html("бери `get_budget`") == (
        "бери <code>get_budget</code>"
    )


def test_fenced_block() -> None:
    assert to_telegram_html("```\n1 + 1\n```") == "<pre>1 + 1</pre>"


def test_html_is_escaped() -> None:
    """Иначе «<» в тексте роняет отправку с 400."""
    assert to_telegram_html("5 < 6 & 7 > 2") == "5 &lt; 6 &amp; 7 &gt; 2"


def test_markup_inside_code_is_left_alone() -> None:
    assert to_telegram_html("`a ** b`") == "<code>a ** b</code>"


def test_angle_brackets_inside_code_are_escaped() -> None:
    assert to_telegram_html("`<b>`") == "<code>&lt;b&gt;</code>"


def test_headers_become_bold() -> None:
    assert to_telegram_html("## Итоги\nтекст") == "<b>Итоги</b>\nтекст"


def test_bullets_become_dots() -> None:
    assert to_telegram_html("- аренда\n- связь") == "• аренда\n• связь"


def test_asterisk_bullets_are_not_italic() -> None:
    assert to_telegram_html("* аренда\n* связь") == "• аренда\n• связь"


def test_links() -> None:
    assert to_telegram_html("[сайт](https://a.ru)") == (
        '<a href="https://a.ru">сайт</a>'
    )


def test_plain_text_survives_untouched() -> None:
    assert to_telegram_html("Записала: Еда → Кофейни, 300 ₽") == (
        "Записала: Еда → Кофейни, 300 ₽"
    )


def test_short_message_is_not_split() -> None:
    assert split_message("привет") == ["привет"]


def test_long_message_splits_on_line_breaks() -> None:
    text = "\n".join(f"строка {i}" * 20 for i in range(500))
    parts = split_message(text)
    assert len(parts) > 1
    assert all(len(p) <= MAX_MESSAGE for p in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_single_huge_line_is_still_cut() -> None:
    """Без переносов резать всё равно надо — иначе телеграм откажет."""
    parts = split_message("я" * (MAX_MESSAGE * 2 + 5))
    assert all(len(p) <= MAX_MESSAGE for p in parts)
    assert "".join(parts) == "я" * (MAX_MESSAGE * 2 + 5)
