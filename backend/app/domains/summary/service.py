"""Бизнес-логика summary: балансы, капитал, потоки.

Read-only домен. Баланс счёта = initial_balance + Σ amount
(знак заложен в данных). Капитал = Σ балансов активных счетов,
пересчитанных в рубли по ТЕКУЩЕМУ курсу (плавающая оценка
«сколько у меня сейчас в рублях»). Архивные счета не считаются.
Cashflow и разбивка по категориям учитывают обычные расходы,
а также проценты и комиссии кредитных платежей по курсу
связанной служебной транзакции.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.datetime import (
    DEFAULT_TIMEZONE,
    date_range_utc,
    month_bounds_utc,
)
from app.core.exceptions import NotFoundError
from app.domains.currencies.service import CurrencyService
from app.domains.summary.repository import SummaryRepository
from app.domains.summary.schemas import (
    AccountBalance,
    ByCategoryResult,
    CashflowResult,
    CategorySpending,
    DailyAllowanceResult,
    DashboardResult,
    MoneyAgeResult,
    Obligation,
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

        # Кредит — обязательство, а не счёт. Без явного вычитания
        # итог показывал бы владельца богаче ровно на сумму долга.
        debt = Decimal(0)
        for credit in await self._repo.active_credits(user_id):
            try:
                rate = await self._currencies.rate_to_rub(credit.currency_code)
            except NotFoundError:
                missing_rate_currencies.add(credit.currency_code)
            else:
                debt += credit.principal_balance * rate

        missing_rates = sorted(missing_rate_currencies)
        return DashboardResult(
            accounts=items,
            total_capital_rub=total - debt,
            total_credit_debt_rub=debt,
            is_total_complete=not missing_rates,
            missing_rate_currencies=missing_rates,
        )

    async def cashflow(
        self,
        user_id: uuid.UUID,
        date_from: date,
        date_to: date,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> CashflowResult:
        start, end = date_range_utc(
            date_from,
            date_to,
            timezone_name,
        )
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
        self,
        user_id: uuid.UUID,
        month: str,
        timezone_name: str = DEFAULT_TIMEZONE,
    ) -> ByCategoryResult:
        month_date = _month_to_date(month)
        start, end = month_bounds_utc(month_date, timezone_name)
        rows = await self._repo.spending_by_category(user_id, start, end)
        items = [
            CategorySpending(category_id=cat_id, amount_rub=abs(total))
            for cat_id, total in rows
        ]
        items.sort(key=lambda x: x.amount_rub, reverse=True)
        total_rub = sum((i.amount_rub for i in items), Decimal(0))
        return ByCategoryResult(month=month, items=items, total_rub=total_rub)

    async def money_age(
        self,
        user_id: uuid.UUID,
        timezone_name: str = DEFAULT_TIMEZONE,
        now: datetime | None = None,
    ) -> MoneyAgeResult:
        """Доход прошлого месяца против расходов текущего.

        Четвёртое правило ВНБ. Месяцы режутся по таймзоне
        пользователя, а не по UTC — иначе у ташкентского вечера
        31 числа месяц окажется предыдущим.
        """
        moment = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone_name))
        current = date(moment.year, moment.month, 1)
        previous = _shift_month(current, -1)

        prev_start, prev_end = month_bounds_utc(previous, timezone_name)
        income, _ = await self._repo.cashflow(user_id, prev_start, prev_end)

        cur_start, cur_end = month_bounds_utc(current, timezone_name)
        _, expense = await self._repo.cashflow(user_id, cur_start, cur_end)
        # Расход хранится отрицательным — берём модуль.
        expense_abs = abs(expense)

        coverage = None if expense_abs == 0 else income / expense_abs
        return MoneyAgeResult(
            previous_month=previous.strftime("%Y-%m"),
            current_month=current.strftime("%Y-%m"),
            previous_month_income_rub=income,
            current_month_expense_rub=expense_abs,
            coverage=coverage,
            is_covered=coverage is None or coverage >= 1,
        )

    async def daily_allowance(
        self,
        user_id: uuid.UUID,
        timezone_name: str = DEFAULT_TIMEZONE,
        until: date | None = None,
        now: datetime | None = None,
    ) -> DailyAllowanceResult:
        """Сколько можно тратить в день до конца горизонта.

        Остаток на счетах — ещё не свободные деньги. Сначала
        резервируем обязательства, которые точно наступят до
        ``until``, и только то, что осталось, делим на дни.
        По умолчанию горизонт — конец текущего месяца.
        """
        moment = (now or datetime.now(UTC)).astimezone(ZoneInfo(timezone_name))
        today = moment.date()
        horizon = until or _end_of_month(today)
        # Горизонт в прошлом — не повод падать: считаем на сегодня.
        horizon = max(horizon, today)
        days_left = (horizon - today).days + 1

        liquid, missing = await self._liquid_rub(user_id)
        month_start = date(today.year, today.month, 1)
        start, end = month_bounds_utc(month_start, timezone_name)
        spent_rows = await self._repo.spending_by_category(user_id, start, end)
        # Траты без категории в резервы не входят: их не с чем сверить.
        spent = {
            cat_id: abs(total)
            for cat_id, total in spent_rows
            if cat_id is not None
        }

        obligations, committed = await self._obligations(
            user_id, today, horizon, spent, missing
        )
        reserved = sum((o.amount_rub for o in obligations), Decimal(0))

        # Обычный лимит по категории дневной лимит не трогает: еда и
        # транспорт — это и есть дневные траты, а не резерв. Копилка
        # (rollover) — наоборот: второе правило ВНБ в том и состоит,
        # что отложенное на страховку сегодня уже не твоё.
        planned_left = Decimal(0)
        for budget in await self._repo.budgets_for_month(user_id, month_start):
            # По одной категории могут стоять и план, и план-минимум.
            # Резервируем большее из двух, а не сумму.
            already = committed.get(budget.category_id, Decimal(0))
            left = (
                budget.planned
                - spent.get(budget.category_id, Decimal(0))
                - already
            )
            if left <= 0:
                continue
            if budget.rollover:
                obligations.append(
                    Obligation(
                        name=_savings_name(budget),
                        amount_rub=left,
                        kind="savings",
                    )
                )
                reserved += left
            else:
                planned_left += left

        safe = liquid - reserved
        # Отрицательный дневной лимит — бессмысленная цифра: тратить
        # «минус восемьсот в день» нельзя, а вот знать о нехватке нужно.
        per_day = (
            (safe / days_left).quantize(Decimal("0.01"))
            if safe > 0
            else Decimal(0)
        )

        missing_rates = sorted(missing)
        return DailyAllowanceResult(
            until=horizon,
            days_left=days_left,
            liquid_rub=liquid,
            obligations_rub=reserved,
            obligations=obligations,
            safe_to_spend_rub=safe,
            per_day_rub=per_day,
            planned_remaining_rub=planned_left,
            unallocated_rub=safe - planned_left,
            is_short=safe < 0,
            is_overplanned=safe - planned_left < 0,
            is_total_complete=not missing_rates,
            missing_rate_currencies=missing_rates,
        )

    async def _liquid_rub(
        self, user_id: uuid.UUID
    ) -> tuple[Decimal, set[str]]:
        """Деньги на активных счетах, пересчитанные в рубли."""
        accounts = await self._repo.active_accounts(user_id)
        balances = await self._repo.balances_by_account(user_id)
        missing: set[str] = set()
        total = Decimal(0)
        for account in accounts:
            balance = (
                balances.get(account.id, Decimal(0)) + account.initial_balance
            )
            try:
                rate = await self._currencies.rate_to_rub(
                    account.currency_code
                )
            except NotFoundError:
                missing.add(account.currency_code)
            else:
                total += balance * rate
        return total, missing

    async def _obligations(
        self,
        user_id: uuid.UUID,
        today: date,
        horizon: date,
        spent: dict[uuid.UUID, Decimal],
        missing: set[str],
    ) -> tuple[list[Obligation], dict[uuid.UUID, Decimal]]:
        """Что точно спишется до горизонта: план-минимум и кредиты.

        Вторым значением — сколько уже зарезервировано по каждой
        категории, чтобы план на ту же категорию не посчитали дважды.
        """
        obligations: list[Obligation] = []
        committed: dict[uuid.UUID, Decimal] = {}

        # План-минимум: резервируем только неоплаченный остаток.
        # Уже потраченное по категории второй раз откладывать незачем.
        for item in await self._repo.active_recurring(user_id):
            planned = item.amount_rub or Decimal(0)
            left = planned - spent.get(item.category_id, Decimal(0))
            if left > 0:
                obligations.append(
                    Obligation(
                        name=item.name, amount_rub=left, kind="recurring"
                    )
                )
                committed[item.category_id] = (
                    committed.get(item.category_id, Decimal(0)) + left
                )

        for credit in await self._repo.active_credits(user_id):
            payment = credit.monthly_payment
            if not payment or not credit.payment_day:
                continue
            try:
                rate = await self._currencies.rate_to_rub(credit.currency_code)
            except NotFoundError:
                missing.add(credit.currency_code)
                continue
            due_dates = _due_dates(credit.payment_day, today, horizon)
            for due in due_dates:
                obligations.append(
                    Obligation(
                        name=f"Платёж по кредиту {due.isoformat()}",
                        amount_rub=payment * rate,
                        kind="credit",
                    )
                )

        return obligations, committed


def _end_of_month(value: date) -> date:
    """Последний день месяца, в котором лежит ``value``."""
    return _shift_month(date(value.year, value.month, 1), 1) - timedelta(
        days=1
    )


def _due_dates(payment_day: int, today: date, horizon: date) -> list[date]:
    """Даты платежей строго после сегодня и не позже горизонта.

    Платёж этого месяца, который уже прошёл, не резервируется:
    деньги за него либо ушли, либо просрочены, и в остатке на счёте
    это уже видно.
    """
    dates: list[date] = []
    cursor = date(today.year, today.month, 1)
    while cursor <= horizon:
        last_day = (_shift_month(cursor, 1) - timedelta(days=1)).day
        # 31-го нет в каждом месяце: списывают в последний день.
        due = date(cursor.year, cursor.month, min(payment_day, last_day))
        if today < due <= horizon:
            dates.append(due)
        cursor = _shift_month(cursor, 1)
    return dates


def _shift_month(value: date, offset: int) -> date:
    """Сдвинуть первое число месяца на ``offset`` месяцев."""
    index = value.year * 12 + value.month - 1 + offset
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def _month_to_date(month: str) -> date:
    """Преобразовать ``YYYY-MM`` в первое число месяца."""
    try:
        year_s, month_s = month.split("-")
        return date(int(year_s), int(month_s), 1)
    except ValueError as exc:
        raise ValueError("Месяц должен быть в формате YYYY-MM.") from exc


def _savings_name(budget: object) -> str:
    """Подпись копилки в списке обязательств.

    Имя категории сюда не дотянуть без лишнего запроса, а заметка к
    лимиту у копилок обычно и есть её название («на зимнюю резину»).
    """
    notes = getattr(budget, "notes", None)
    return str(notes) if notes else "Копилка"
