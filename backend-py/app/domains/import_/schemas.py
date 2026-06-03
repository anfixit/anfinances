"""Pydantic-схемы домена import_.

Тело ``POST /import/all`` — это ``ExportBundle`` (формат бэкапа из
домена export), поэтому отдельная схема не нужна. Здесь — массовый
импорт транзакций и сводка результата восстановления.
"""

from pydantic import BaseModel

from app.domains.transactions.schemas import TransactionCreate

__all__ = ["ImportResult", "ImportTransactions"]


class ImportTransactions(BaseModel):
    items: list[TransactionCreate]


class ImportResult(BaseModel):
    """Сколько строк восстановлено из бэкапа по каждой сущности."""

    accounts: int
    categories: int
    transfers: int
    transactions: int
    budgets: int
    recurring: int
    currencies: int
