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


def test_text_named_xlsx_is_read_as_a_statement(tmp_path: Path) -> None:
    """Некоторые банки называют .xlsx обычный текст."""
    path = tmp_path / "v.xlsx"
    path.write_bytes("дата;сумма\n01.08.2026;-300".encode())
    assert "01.08.2026" in read_spreadsheet(path)


def test_old_xls_is_named_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "v.xlsx"
    path.write_bytes(b"\xd0\xcf\x11\xe0" + b"0" * 40)
    with pytest.raises(DocumentUnreadableError, match=r"\.xls"):
        read_spreadsheet(path)


def test_broken_zip_reports_the_real_cause(tmp_path: Path) -> None:
    """«Выгрузи CSV» ничего не объясняет без причины."""
    path = tmp_path / "v.xlsx"
    path.write_bytes(b"PK\x03\x04" + b"0" * 40)
    with pytest.raises(DocumentUnreadableError) as caught:
        read_spreadsheet(path)
    assert "Error" in str(caught.value) or "zip" in str(caught.value).lower()


def test_password_protected_pdf_is_named(tmp_path: Path) -> None:
    """Модель получит такой файл, но не увидит в нём ни строчки."""
    path = tmp_path / "v.pdf"
    path.write_bytes(
        b"%PDF-1.4\n" + b"0" * 100 + b"/Encrypt 9 0 R\ntrailer\n%%EOF"
    )
    with pytest.raises(DocumentUnreadableError, match="паролем"):
        read_pdf(path)


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


def test_spreadsheet_without_extension_is_read(tmp_path: Path) -> None:
    """Скачанное вложение лежит во временном файле без расширения.

    openpyxl определяет формат по имени файла и отказывался открывать
    даже настоящий xlsx — отсюда «does not support  file format».
    """
    path = tmp_path / "attachment"
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["дата", "сумма"])
    sheet.append(["01.08.2026", -300])
    book.save(path)

    assert "01.08.2026;-300" in read_spreadsheet(path)
