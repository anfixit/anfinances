"""Инструменты агента.

Каждый инструмент — тонкая обёртка над HTTP-вызовом anfinances.
Инструментов на удаление счетов, категорий и кредитов, на правку
настроек, валют и начального баланса здесь нет: это осознанная
граница полномочий бота. Ошибиться в распознанной речи легко, а
такие действия не откатываются одной кнопкой.

Докстроки методов уходят в описание инструментов для модели, а
сигнатуры — в схему параметров. Это контракт, а не украшение.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from anthropic import beta_async_tool

from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead
from anfinances_bot.resolve.accounts import resolve_account
from anfinances_bot.resolve.categories import (
    build_category_paths,
    find_category_by_path,
)

__all__ = ["ToolBox"]

# Сколько путей категорий показывать модели в тексте ошибки.
_MAX_HINTS = 40


class _Client(Protocol):
    async def accounts(self) -> list[AccountRead]: ...
    async def categories(self) -> list[CategoryRead]: ...
    async def request(self, method: str, path: str, **kwargs: Any) -> Any: ...


class ToolBox:
    def __init__(
        self,
        client: _Client,
        default_accounts: dict[str, str],
        timezone: str,
    ) -> None:
        self._client = client
        self._default_accounts = default_accounts
        self._tz = ZoneInfo(timezone)
        # Нужны хендлеру, чтобы показать карточку и кнопки выбора.
        self.last_created_id: str | None = None
        self.pending_accounts: list[AccountRead] = []

        # Схемы инструментов выводятся из сигнатур и докстрок методов.
        self.tools = [
            beta_async_tool(method)
            for method in (
                self.create_expense,
                self.create_income,
                self.create_transfer,
                self.create_credit_payment,
                self.list_accounts,
                self.list_categories,
                self.get_capital,
                self.get_by_category,
                self.get_budget,
                self.list_transactions,
                self.get_credits,
                self.get_credit_projection,
                self.get_money_age,
            )
        ]

    # --- запись ---------------------------------------------------

    async def create_expense(
        self,
        amount: str,
        category_path: str,
        account_name: str | None = None,
        currency_code: str | None = None,
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Записать трату.

        amount — положительное число строкой, знак ставит anfinances.
        category_path — полный путь вида «Еда → Кофейни»; выдумывать
        категории нельзя, только выбирать из существующих.
        account_name — название счёта, если оно прозвучало.
        currency_code — валюта траты (RUB, UZS, USD), если названа.
        when — ISO-дата или дата со временем; по умолчанию сейчас.
        """
        return await self._ordinary(
            "expense",
            amount,
            category_path,
            account_name,
            currency_code,
            when,
            comment,
        )

    async def create_income(
        self,
        amount: str,
        category_path: str,
        account_name: str | None = None,
        currency_code: str | None = None,
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Записать доход. Параметры те же, что у create_expense.

        Категория берётся из доходного дерева: расходные пути здесь
        не подойдут.
        """
        return await self._ordinary(
            "income",
            amount,
            category_path,
            account_name,
            currency_code,
            when,
            comment,
        )

    async def create_transfer(
        self,
        from_account_name: str,
        to_account_name: str,
        amount_from: str,
        amount_to: str,
        when: str | None = None,
        fee_amount: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Перевод между своими счетами.

        Обе суммы обязательны: пара реальных сумм фиксирует
        фактический курс обмена. Досчитывать вторую по рыночному
        курсу нельзя — переспроси у пользователя, сколько пришло.
        fee_amount — комиссия, если она снялась отдельно.
        """
        if not amount_from or not amount_to:
            raise ValueError(
                "Нужны обе суммы: сколько ушло и сколько пришло. "
                "Спроси у пользователя вторую сумму."
            )
        accounts = await self._client.accounts()
        source = _find_account(accounts, from_account_name)
        target = _find_account(accounts, to_account_name)
        if source is None or target is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"

        body: dict[str, Any] = {
            "from_account_id": source.id,
            "to_account_id": target.id,
            "amount_from": str(amount_from),
            "amount_to": str(amount_to),
            "date": self._moment(when),
        }
        if fee_amount:
            body["fee_amount"] = str(fee_amount)
        if comment:
            body["comment"] = comment

        await self._client.request("POST", "/transfers", json=body)
        return (
            f"Перевод записан: {source.name} → {target.name}, "
            f"{amount_from} → {amount_to}"
        )

    async def create_credit_payment(
        self,
        credit_id: str,
        total_amount: str,
        principal_amount: str,
        interest_amount: str = "0",
        fee_amount: str = "0",
        account_name: str | None = None,
        interest_category_path: str | None = None,
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Записать платёж по кредиту.

        Платёж делится на тело, проценты и комиссию; их сумма обязана
        равняться total_amount. Разбивку надо взять у пользователя —
        она есть в приложении банка и по ней считается остаток долга.
        Досрочный платёж вносится так же: там просто почти всё уходит
        в тело, и срок кредита сокращается сам.
        """
        try:
            total = Decimal(total_amount)
            parts = (
                Decimal(principal_amount)
                + Decimal(interest_amount)
                + Decimal(fee_amount)
            )
        except InvalidOperation:
            return "Суммы должны быть числами."
        if parts != total:
            return (
                f"Разбивка не сходится: тело, проценты и комиссия дают "
                f"{parts}, а платёж — {total}. Уточни у пользователя, "
                "сколько ушло в тело и сколько в проценты."
            )

        accounts = await self._client.accounts()
        resolution = resolve_account(
            accounts,
            named=account_name,
            currency_code=None,
            history_account_id=None,
            default_names=self._default_accounts,
        )
        if resolution.account is None:
            self.pending_accounts = resolution.candidates
            names = ", ".join(a.name for a in resolution.candidates)
            return f"Надо уточнить счёт списания. Варианты: {names}"

        body: dict[str, Any] = {
            "payment_account_id": resolution.account.id,
            "date": self._moment(when),
            "total_amount": str(total_amount),
            "principal_amount": str(principal_amount),
            "interest_amount": str(interest_amount),
            "fee_amount": str(fee_amount),
        }
        if interest_category_path:
            categories = await self._client.categories()
            paths = build_category_paths(categories, kind="expense")
            found = find_category_by_path(paths, interest_category_path)
            if found is None:
                return _unknown_category(interest_category_path, paths)
            body["interest_category_id"] = found.id
        if comment:
            body["comment"] = comment

        created = await self._client.request(
            "POST", f"/credits/{credit_id}/payments", json=body
        )
        self.last_created_id = created["id"]
        return (
            f"Платёж записан: {total_amount} "
            f"(тело {principal_amount}, проценты {interest_amount}), "
            f"{resolution.account.name}"
        )

    # --- чтение ---------------------------------------------------

    async def list_accounts(self) -> str:
        """Счета пользователя с остатками и валютами."""
        accounts = await self._client.accounts()
        return "\n".join(
            f"{a.name}: {a.current_balance} {a.currency_code}"
            for a in accounts
        )

    async def list_categories(self, kind: str = "expense") -> str:
        """Дерево категорий путями. kind: expense или income."""
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind=kind)
        return "\n".join(p.path for p in paths)

    async def get_capital(self) -> str:
        """Капитал: остатки по счетам, итог в рублях и долг по кредитам."""
        return str(await self._client.request("GET", "/summary/dashboard"))

    async def get_by_category(self, month: str) -> str:
        """Расходы по категориям за месяц в формате YYYY-MM."""
        return str(
            await self._client.request(
                "GET", "/summary/by-category", params={"month": month}
            )
        )

    async def get_budget(self, month: str) -> str:
        """Бюджет и его исполнение за месяц в формате YYYY-MM."""
        return str(
            await self._client.request(
                "GET", "/budgets", params={"month": month}
            )
        )

    async def list_transactions(
        self,
        limit: int = 20,
        category_id: str | None = None,
        account_id: str | None = None,
    ) -> str:
        """Последние операции.

        Полезно, чтобы понять, куда пользователь обычно относит
        похожую трату, вместо того чтобы переспрашивать.
        """
        params: dict[str, Any] = {"limit": limit}
        if category_id:
            params["category_id"] = category_id
        if account_id:
            params["account_id"] = account_id
        return str(
            await self._client.request("GET", "/transactions", params=params)
        )

    async def get_credits(self) -> str:
        """Кредиты: остаток долга, ставка, срок, обязательный платёж."""
        return str(await self._client.request("GET", "/credits"))

    async def get_credit_projection(self, credit_id: str) -> str:
        """Сколько платежей осталось и как делится ближайший.

        Считается от текущего остатка, поэтому досрочное погашение
        сразу видно как сокращение срока.
        """
        return str(
            await self._client.request(
                "GET", f"/credits/{credit_id}/projection"
            )
        )

    async def get_money_age(self) -> str:
        """Покрыты ли траты этого месяца доходом прошлого."""
        return str(await self._client.request("GET", "/summary/money-age"))

    # --- внутреннее -----------------------------------------------

    async def _ordinary(
        self,
        kind: str,
        amount: str,
        category_path: str,
        account_name: str | None,
        currency_code: str | None,
        when: str | None,
        comment: str | None,
    ) -> str:
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind=kind)
        category = find_category_by_path(paths, category_path)
        if category is None:
            return _unknown_category(category_path, paths)

        accounts = await self._client.accounts()
        resolution = resolve_account(
            accounts,
            named=account_name,
            currency_code=currency_code,
            history_account_id=None,
            default_names=self._default_accounts,
        )
        if resolution.account is None:
            self.pending_accounts = resolution.candidates
            names = ", ".join(a.name for a in resolution.candidates)
            return f"Надо уточнить счёт у пользователя. Варианты: {names}"

        body: dict[str, Any] = {
            "account_id": resolution.account.id,
            "kind": kind,
            "amount": str(amount),
            "date": self._moment(when),
            "category_id": category.id,
        }
        if comment:
            body["comment"] = comment

        created = await self._client.request(
            "POST", "/transactions", json=body
        )
        self.last_created_id = created["id"]
        return (
            f"Записано: {category.path} — {amount}, {resolution.account.name}"
        )

    def _moment(self, when: str | None) -> str:
        """Превратить сказанное время в UTC-метку.

        Пользователь говорит в своём часовом поясе, а хранится всё в
        UTC. Без пересчёта «вчера вечером» в Ташкенте уехало бы на
        сутки вперёд.
        """
        if not when:
            return datetime.now(UTC).isoformat()
        try:
            parsed = datetime.fromisoformat(when)
        except ValueError:
            return datetime.now(UTC).isoformat()
        if len(when) <= 10:
            # Голая дата: ставим полдень, чтобы пересчёт часового
            # пояса не перекинул операцию в соседние сутки.
            parsed = parsed.replace(hour=12)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self._tz)
        return parsed.astimezone(UTC).isoformat()


def _unknown_category(path: str, paths: list[Any]) -> str:
    available = ", ".join(p.path for p in paths[:_MAX_HINTS])
    return (
        f"Категория «{path}» не найдена. Выбери из существующих "
        f"или спроси пользователя. Доступные: {available}"
    )


def _find_account(
    accounts: list[AccountRead], name: str
) -> AccountRead | None:
    """Найти счёт по названию: точное совпадение, затем однозначное."""
    needle = name.casefold()
    for account in accounts:
        if account.name.casefold() == needle:
            return account
    matches = [a for a in accounts if needle in a.name.casefold()]
    return matches[0] if len(matches) == 1 else None
