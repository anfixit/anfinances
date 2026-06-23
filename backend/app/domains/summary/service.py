"""Бизнес-логика summary: балансы, капитал, потоки.

Read-only домен. Баланс счёта = initial_balance + Σ amount
(знак заложен в данных). Капитал = Σ балансов активных счетов,
пересчитанных в рубли по ТЕКУЩЕМУ курсу (плавающая оценка
«сколько у меня сейчас в рублях»). Архивные счета не считаются.
Cashflow и разбивка по категориям — по запечённым amount_rub.
"""

import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import NotFoundError
from app.domains.currencies.service import CurrencyService
from app.domains.summary.repository import SummaryRepository
from app.domains.summary.schemas import (
    AccountBalance,
    ByCategoryResult,
    CashflowResult,
    CategorySpending,
    DashboardResult,
)

__all__ = ["SummaryService"]


class SummaryService:
    def __init__(
        self,
        repo: SummaryRepository,
        currencies: CurrencyService,
    ) -> None:
        self._repo = repo
        self._currencies = currencies

    async def dashboard(self, user_id: uuid.UUID) -> DashboardResult:
        accounts = await self._repo.active_accounts(user_id)
        balances = await self._repo.balances_by_account(user_id)

        items: list[AccountBalance] = []
        missing_rate_currencies: set[str] = set()
        total = Decimal(0)

        for account in accounts:
            balance = (
                balances.get(account.id, Decimal(0)) + account.initial_balance
            )
            balance_rub: Decimal | None

            try:
                rate = await self._currencies.rate_to_rub(
                    account.currency_code
                )
            except NotFoundError:
                balance_rub = None
                missing_rate_currencies.add(account.currency_code)
            else:
                balance_rub = balance * rate
                total += balance_rub

            items.append(
                AccountBalance(
                    account_id=account.id,
                    name=account.name,
                    currency_code=account.currency_code,
                    balance=balance,
                    balance_rub=balance_rub,
                )
            )

        missing_rates = sorted(missing_rate_currencies)
        return DashboardResult(
            accounts=items,
            total_capital_rub=total,
            is_total_complete=not missing_rates,
            missing_rate_currencies=missing_rates,
        )

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> CashflowResult:
        start = datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(date_to, datetime.max.time(), tzinfo=UTC)
        income, expense = await self._repo.cashflow(user_id, start, end)
        # expense хранится отрицательным — модуль для отображения
        expense_abs = abs(expense)
        return CashflowResult(
            date_from=date_from,
            date_to=date_to,
            income_rub=income,
            expense_rub=expense_abs,
            net_rub=income - expense_abs,
        )

    async def by_category(
        self, user_id: uuid.UUID, month: str
    ) -> ByCategoryResult:
        start, end = _month_bounds(month)
        rows = await self._repo.spending_by_category(user_id, start, end)
        items = [
            CategorySpending(category_id=cat_id, amount_rub=abs(total))
            for cat_id, total in rows
        ]
        items.sort(key=lambda x: x.amount_rub, reverse=True)
        total_rub = sum((i.amount_rub for i in items), Decimal(0))
        return ByCategoryResult(month=month, items=items, total_rub=total_rub)


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """Границы месяца 'YYYY-MM' → (начало, конец) в UTC."""
    try:
        year_s, mon_s = month.split("-")
        year, mon = int(year_s), int(mon_s)
        last_day = calendar.monthrange(year, mon)[1]
    except ValueError as exc:
        raise ValueError("Месяц должен быть в формате YYYY-MM.") from exc
    start = datetime(year, mon, 1, tzinfo=UTC)
    end = datetime(year, mon, last_day, 23, 59, 59, 999999, tzinfo=UTC)
    return start, end
