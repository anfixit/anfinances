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
    """Тип операции.

    Три последних — деньги, которые приходят или правятся, но не
    являются ни заработком, ни тратой. Пока их не было, кредит на
    430 000 и возврат с Ozon записывались доходом, и график доходов
    показывал плюс там, где был минус.

    LOAN — получение кредита: остаток растёт, но это долг.
    REFUND — возврат: ложится в категорию траты и уменьшает её.
    ADJUSTMENT — корректировка учёта после сверки, со своим знаком.
    """

    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"
    CREDIT_PAYMENT = "credit_payment"
    LOAN = "loan"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


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
