"""Чтение присланных файлов — банковских выписок.

Разбирать формат конкретного банка кодом бессмысленно: у каждого
свои колонки, разделители и названия. Поэтому файл превращается в
текст, а разбор делает модель — она справляется с любой шапкой.
"""

import base64
import csv
import io
import logging
from pathlib import Path

logger = logging.getLogger("anfinances_bot.documents")

__all__ = [
    "MAX_CHARS",
    "MAX_IMAGE_BYTES",
    "DocumentUnreadableError",
    "read_image",
    "read_statement",
]

# Сколько текста выписки отдаём модели. Больше — и ответ упрётся в
# окно контекста, а выписка на несколько тысяч строк всё равно
# просится разбитой по месяцам.
MAX_CHARS = 60_000

_ENCODINGS = ("utf-8-sig", "cp1251", "utf-16")


class DocumentUnreadableError(RuntimeError):
    """Файл не удалось прочитать как текст."""


def read_statement(path: Path) -> str:
    """Прочитать выписку в текст, что бы банк ни выгрузил.

    Российские банки любят cp1251 и точку с запятой, поэтому
    кодировки перебираются, а не угадываются по расширению.
    """
    raw = path.read_bytes()
    if not raw.strip():
        raise DocumentUnreadableError("Файл пустой.")

    text = None
    for encoding in _ENCODINGS:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        else:
            break
    if text is None:
        raise DocumentUnreadableError(
            "Это не текстовый файл. Нужен CSV или TXT."
        )

    text = text.replace("\x00", "").strip()
    if not text:
        raise DocumentUnreadableError("Файл пустой.")

    if len(text) > MAX_CHARS:
        text = _head_rows(text)
    return text


def _head_rows(text: str) -> str:
    """Обрезать по строкам и честно сказать, что обрезано."""
    kept: list[str] = []
    total = 0
    for line in text.splitlines():
        if total + len(line) > MAX_CHARS:
            break
        kept.append(line)
        total += len(line) + 1
    logger.warning("Выписка обрезана до %s строк", len(kept))
    return "\n".join(kept) + (
        "\n\n[Файл обрезан: слишком длинный. Занеси показанное и "
        "попроси прислать остаток отдельным файлом.]"
    )


def sniff_delimiter(text: str) -> str:
    """Угадать разделитель — подсказка модели, а не разбор."""
    sample = "\n".join(text.splitlines()[:5])
    try:
        return str(csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter)
    except (csv.Error, io.UnsupportedOperation):
        return ";"


# Скриншот чека, выписки или экрана банка. Клод принимает эти
# четыре типа; телеграм при пересылке фото отдаёт jpeg.
IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Предел на изображение в запросе к модели.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def read_image(path: Path, filename: str = "") -> tuple[str, str]:
    """Прочитать картинку как пару «media_type, base64»."""
    raw = path.read_bytes()
    if not raw:
        raise DocumentUnreadableError("Файл пустой.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise DocumentUnreadableError(
            "Картинка больше 5 МБ. Пришли скриншот поменьше."
        )

    media_type = _media_type(raw, filename)
    if media_type is None:
        raise DocumentUnreadableError(
            "Не похоже на картинку. Нужен jpg, png, webp или gif."
        )
    return media_type, base64.b64encode(raw).decode("ascii")


def _media_type(raw: bytes, filename: str) -> str | None:
    """Тип по сигнатуре файла, а не по расширению.

    Телеграм отдаёт фото без имени, а присланный «скриншот.pdf»
    именем врёт. Первые байты не врут.
    """
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF8"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return IMAGE_TYPES.get(Path(filename).suffix.lower())
