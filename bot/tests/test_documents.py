"""Чтение вложений: форматы, кодировки и пределы."""

import base64
from pathlib import Path

import pytest
from openpyxl import Workbook

from anfinances_bot.documents import (
    DocumentUnreadableError,
    read_image,
    read_pdf,
    read_spreadsheet,
    read_statement,
)


def test_cp1251_statement_is_read(tmp_path: Path) -> None:
    """Российские банки выгружают в cp1251, а не в utf-8."""
    path = tmp_path / "v.csv"
    path.write_bytes("дата;сумма\n01.08.2026;-300".encode("cp1251"))
    assert "сумма" in read_statement(path)


def test_empty_statement_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "v.csv"
    path.write_bytes(b"   ")
    with pytest.raises(DocumentUnreadableError):
        read_statement(path)


def test_pdf_is_returned_as_base64(tmp_path: Path) -> None:
    path = tmp_path / "v.pdf"
    path.write_bytes(b"%PDF-1.7\n" + "тело".encode())
    assert base64.b64decode(read_pdf(path)).startswith(b"%PDF")


def test_file_pretending_to_be_pdf_is_rejected(tmp_path: Path) -> None:
    """Расширение врёт, первые байты — нет."""
    path = tmp_path / "v.pdf"
    path.write_bytes(b"PK\x03\x04" + " это zip".encode())
    with pytest.raises(DocumentUnreadableError):
        read_pdf(path)


def test_spreadsheet_rows_become_lines(tmp_path: Path) -> None:
    path = tmp_path / "v.xlsx"
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["дата", "сумма", "назначение"])
    sheet.append(["01.08.2026", -300, "кофе"])
    sheet.append([None, None, None])
    book.save(path)

    text = read_spreadsheet(path)
    assert "дата;сумма;назначение" in text
    assert "01.08.2026;-300;кофе" in text
    # Пустые строки в выгрузках банка идут пачками — они лишние.
    assert ";;" not in text


def test_broken_spreadsheet_asks_for_csv(tmp_path: Path) -> None:
    path = tmp_path / "v.xlsx"
    path.write_bytes("не таблица".encode())
    with pytest.raises(DocumentUnreadableError, match="CSV"):
        read_spreadsheet(path)


def test_image_type_comes_from_the_first_bytes(tmp_path: Path) -> None:
    """Телеграм отдаёт фото без имени, а «скриншот.pdf» именем врёт."""
    path = tmp_path / "shot.pdf"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    media_type, data = read_image(path, "shot.pdf")
    assert media_type == "image/png"
    assert base64.b64decode(data).startswith(b"\x89PNG")


def test_non_image_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "shot.bin"
    path.write_bytes("просто байты".encode())
    with pytest.raises(DocumentUnreadableError):
        read_image(path, "shot.bin")
