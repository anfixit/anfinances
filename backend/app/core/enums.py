"""Доменные перечисления, общие для нескольких моделей.

Значения совпадают с тем, что хранится в БД (нативный PG enum).
StrEnum даёт строковую сериализацию в JSON без доп. конвертеров.
"""

from enum import StrEnum


class AccountType(StrEnum):
    CARD = "card"
    CASH = "cash"
    CARD_CREDIT = "card_credit"
    SAVINGS = "savings"
    INVESTMENT = "investment"


class CategoryKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class TransactionKind(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    CREDIT_PAYMENT = "credit_payment"


class RequiredKind(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"


class OAuthProvider(StrEnum):
    GOOGLE = "google"
    GITHUB = "github"
    VK = "vk"
    YANDEX = "yandex"
    ODNOKLASSNIKI = "odnoklassniki"


class GoalKind(StrEnum):
    """Вид цели по категории.

    MONTHLY — нужно столько каждый месяц (подписка, аренда).
    BY_DATE — нужно накопить столько к дате (страховка, отпуск).
    """

    MONTHLY = "monthly"
    BY_DATE = "by_date"
