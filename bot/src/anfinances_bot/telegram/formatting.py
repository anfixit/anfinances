"""Markdown модели → HTML телеграма.

Модель пишет обычным markdown, а телеграм его не понимает: без
разметки в чат приезжают голые звёздочки. MarkdownV2 требует
экранировать полтора десятка символов, и любая пропущенная точка
роняет отправку, поэтому переводим в HTML — там экранировать надо
ровно три символа.
"""

import html
import re

__all__ = ["MAX_MESSAGE", "split_message", "to_telegram_html"]

# Предел телеграма на одно сообщение.
MAX_MESSAGE = 4096

_FENCED = re.compile(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HEADER = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")
_ITALIC_UNDER = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")

_PLACEHOLDER = "\x00{}\x00"


def to_telegram_html(text: str) -> str:
    """Перевести markdown в подмножество HTML, понятное телеграму."""
    chunks: list[str] = []

    def _stash(rendered: str) -> str:
        chunks.append(rendered)
        return _PLACEHOLDER.format(len(chunks) - 1)

    # Код прячем первым: внутри него разметку трогать нельзя.
    def _fenced(match: re.Match[str]) -> str:
        body = html.escape(match.group(1).strip("\n"), quote=False)
        return _stash(f"<pre>{body}</pre>")

    def _inline(match: re.Match[str]) -> str:
        body = html.escape(match.group(1), quote=False)
        return _stash(f"<code>{body}</code>")

    text = _FENCED.sub(_fenced, text)
    text = _INLINE_CODE.sub(_inline, text)

    # Списки — до курсива, иначе «* пункт» станет открывающей звёздочкой.
    text = _BULLET.sub(r"\1• ", text)
    text = html.escape(text, quote=False)

    text = _HEADER.sub(r"<b>\1</b>", text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)
    text = _ITALIC_STAR.sub(r"<i>\1</i>", text)
    text = _ITALIC_UNDER.sub(r"<i>\1</i>", text)

    for index, rendered in enumerate(chunks):
        text = text.replace(_PLACEHOLDER.format(index), rendered)
    return text


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Порезать длинный текст на куски по границам строк.

    Режем исходный текст, а не готовый HTML: так тег не окажется
    разорванным между сообщениями.
    """
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            # Строка длиннее предела — режем как есть, вариантов нет.
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return parts
