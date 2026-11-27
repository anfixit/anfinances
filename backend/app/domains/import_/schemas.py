"""Pydantic-схемы домена import_.

Тело ``POST /import/all`` — это ``ExportBundle`` (формат бэкапа из
домена export), поэтому отдельная схема не нужна. Здесь — массовый
импорт транзакций и сводка результата восстановления.
"""

from pydantic import BaseModel, Field

from app.domains.transactions.schemas import TransactionCreate

__all__ = ["ImportResult", "ImportTransactions"]


class ImportTransactions(BaseModel):
    # Выписка за месяц — сотни строк; потолок не даёт одним запросом
    # положить базу тысячами вставок.
    items: list[TransactionCreate] = Field(max_length=2000)


class ImportResult(BaseModel):
    """Сколько строк восстановлено из бэкапа по каждой сущности."""

    accounts: int
    categories: int
    transfers: int
    transactions: int
    budgets: int
    recurring: int
    currencies: int
    # Появились в бэкапе версии 2; у версии 1 их нет — отсюда нули.
    credits: int = 0
    credit_payments: int = 0
    payees: int = 0
    # Появились в бэкапе версии 3.
    payee_candidates: int = 0
    goals: int = 0
    reconciliations: int = 0
