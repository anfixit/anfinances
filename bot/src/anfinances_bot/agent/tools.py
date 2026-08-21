"""Инструменты агента.

Каждый инструмент — тонкая обёртка над HTTP-вызовом anfinances.
Бот дотягивается до всего, что умеет сайт: заводит, правит, убирает
в архив и удаляет — операции, переводы, счета, категории, кредиты,
их платежи, планы и план-минимум.

Двух вещей здесь нет намеренно. Начальный баланс счёта не правится:
после первой операции он заблокирован и на сайте, а исправлять
остаток надо операцией, а не переписыванием прошлого. Настройки
профиля и справочник валют тоже не трогаются — это не ежедневная
работа, и цена ошибки в распознанной речи выше пользы.

Разрушительное действие бот совершает только после явного согласия
в переписке; за это отвечает системная инструкция.

Докстроки методов уходят в описание инструментов для модели, а
сигнатуры — в схему параметров. Это контракт, а не украшение.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from anthropic import beta_async_tool
from pydantic import BaseModel

from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead
from anfinances_bot.resolve.accounts import resolve_account
from anfinances_bot.resolve.categories import (
    build_category_paths,
    find_category_by_path,
)

__all__ = ["StatementRow", "ToolBox"]

# Сколько путей категорий показывать модели в тексте ошибки.
_MAX_HINTS = 40

# Размер страницы /transactions — потолок, заданный самим API.
_PAGE = 100
# Предохранитель от бесконечного листания, если API поведёт себя
# не так, как ожидается: 10 000 операций по счёту за период хватит.
_MAX_PAGES = 100

# Сколько строк разбора показывать в ответе модели. Выписка за месяц
# бывает на две сотни строк, а её ещё надо прочитать в телеграме.
_PREVIEW_LINES = 40

_ACCOUNT_TYPES = frozenset(
    {"card", "cash", "card_credit", "savings", "investment"}
)


class StatementRow(BaseModel):
    """Одна строка банковской выписки, уже разобранная моделью."""

    date: str
    amount: str
    kind: Literal["expense", "income"]
    category_path: str
    comment: str | None = None


@dataclass
class PendingImport:
    """Разобранная выписка, ждущая её согласия.

    Разбор и запись разведены намеренно. Пока они были одним вызовом,
    бот заносил десятки строк, не показав их, и отменять приходилось
    руками по одной. Теперь ``preview_statement`` только считает и
    показывает, а ``import_statement`` пишет — и только на следующем
    ходу, когда она успела ответить.
    """

    token: str
    account_id: str
    account_name: str
    items: list[dict[str, Any]]
    duplicates: int
    lines: list[str]
    # Ставится в True при следующем запуске агента, то есть после её
    # ответа. В том же ходу, где показали разбор, занести нельзя.
    confirmed: bool = False


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
        self.pending_import: PendingImport | None = None
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
                self.preview_statement,
                self.import_statement,
                self.update_transaction,
                self.delete_transaction,
                self.delete_transfer,
                self.update_account,
                self.restore_account,
                self.update_category,
                self.archive_category,
                self.update_credit,
                self.archive_credit,
                self.delete_budget,
                self.delete_credit_payment,
                self.archive_account,
                self.set_budget,
                self.move_budget,
                self.create_category,
                self.create_account,
                self.create_credit,
                self.add_recurring,
                self.update_recurring,
                self.delete_recurring,
                self.list_accounts,
                self.list_categories,
                self.list_recurring,
                self.get_capital,
                self.get_by_category,
                self.get_budget,
                self.get_daily_allowance,
                self.list_transactions,
                self.get_credits,
                self.get_credit_projection,
                self.get_money_age,
                self.list_credit_payments,
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

    async def update_transaction(
        self,
        transaction_id: str,
        amount: str | None = None,
        category_path: str | None = None,
        account_name: str | None = None,
        kind: str = "expense",
        when: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Поправить уже записанную операцию.

        Меняются только переданные поля. Счёт сменить можно — если
        валюта нового счёта другая, рублёвая оценка пересчитается
        сама. Тип операции сменить нельзя: расход вместо дохода —
        это другая операция, её надо удалить и записать заново.
        kind нужен, чтобы искать категорию в нужном дереве.
        """
        body: dict[str, Any] = {}
        if account_name:
            accounts = await self._client.accounts()
            account = _find_account(accounts, account_name)
            if account is None:
                names = ", ".join(a.name for a in accounts)
                return f"Счёт не найден. Доступные: {names}"
            body["account_id"] = account.id
        if amount:
            body["amount"] = str(amount)
        if when:
            body["date"] = self._moment(when)
        if comment is not None:
            body["comment"] = comment
        if category_path:
            categories = await self._client.categories()
            paths = build_category_paths(categories, kind=kind)
            found = find_category_by_path(paths, category_path)
            if found is None:
                return _unknown_category(category_path, paths)
            body["category_id"] = found.id
        if not body:
            return "Нечего менять: не передано ни одно поле."

        await self._client.request(
            "PATCH", f"/transactions/{transaction_id}", json=body
        )
        return "Операция исправлена."

    async def delete_transaction(self, transaction_id: str) -> str:
        """Удалить операцию, записанную по ошибке.

        Только операции: счета, категории и кредиты бот не удаляет.
        """
        await self._client.request("DELETE", f"/transactions/{transaction_id}")
        return "Операция удалена."

    async def preview_statement(
        self, account_name: str, rows: list[StatementRow]
    ) -> str:
        """Разобрать выписку и показать, что будет занесено.

        Ничего не записывает. Сверяет строки с уже записанным по
        этому счёту и возвращает список только новых операций плюс
        число пропущенных дублей.

        Все строки должны быть по одному счёту. Категории проставь
        сам по назначению платежа, опираясь на дерево категорий и на
        прошлые операции; выдумывать новые пути нельзя.

        Полученный список покажи ей целиком и дождись ответа. Занести
        его потом можно вызовом import_statement с выданным токеном —
        раньше её ответа он всё равно откажет.
        """
        if not rows:
            return "Список операций пуст — нечего заносить."

        accounts = await self._client.accounts()
        account = _find_account(accounts, account_name)
        if account is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"

        categories = await self._client.categories()
        trees = {
            kind: build_category_paths(categories, kind=kind)
            for kind in ("expense", "income")
        }

        resolved: list[dict[str, Any]] = []
        labels: list[str] = []
        unknown: set[str] = set()
        for raw in rows:
            # Модель присылает JSON; в тестах и при прямом вызове —
            # уже готовые объекты. Принимаем и то, и другое.
            row = StatementRow.model_validate(raw)
            paths = trees.get(row.kind, [])
            found = find_category_by_path(paths, row.category_path)
            if found is None:
                unknown.add(row.category_path)
                continue
            item: dict[str, Any] = {
                "account_id": account.id,
                "kind": row.kind,
                "amount": str(row.amount),
                "date": self._moment(row.date),
                "category_id": found.id,
            }
            if row.comment:
                item["comment"] = row.comment
            resolved.append(item)
            labels.append(_row_label(row))

        # Молча пропустить строку — потерять операцию незаметно.
        # Лучше не заносить ничего и показать, что не разобралось.
        if unknown:
            self.pending_import = None
            return (
                "Не нашла категории: "
                + ", ".join(sorted(unknown))
                + ". Подбери существующие пути и повтори — "
                "ничего не занесено."
            )

        seen = await self._existing_keys(account.id, resolved)
        fresh: list[dict[str, Any]] = []
        lines: list[str] = []
        duplicates = 0
        for item, label in zip(resolved, labels, strict=True):
            key = (item["date"][:10], _norm_amount(item["amount"]))
            if key in seen:
                duplicates += 1
                continue
            fresh.append(item)
            lines.append(label)

        if not fresh:
            self.pending_import = None
            return (
                f"Разобрала выписку по счёту «{account.name}». Все "
                f"{duplicates} операций уже записаны раньше — "
                "заносить нечего."
            )

        token = secrets.token_hex(4)
        self.pending_import = PendingImport(
            token=token,
            account_id=account.id,
            account_name=account.name,
            items=fresh,
            duplicates=duplicates,
            lines=lines,
        )
        shown = lines[:_PREVIEW_LINES]
        rest = len(lines) - len(shown)
        body = "\n".join(shown)
        if rest > 0:
            body += f"\n…и ещё {rest}"
        skipped = (
            f" Уже записано раньше и будет пропущено: {duplicates}."
            if duplicates
            else " Дублей с уже записанным нет."
        )
        return (
            f"Разобрала выписку по счёту «{account.name}». "
            f"Новых операций: {len(fresh)}.{skipped}\n\n"
            f"{body}\n\n"
            f"Покажи этот список целиком и спроси, заносить ли. "
            f"Токен для записи: {token}."
        )

    async def import_statement(self, token: str) -> str:
        """Занести разобранную выписку после её согласия.

        token — из ответа preview_statement. Вызывать только тогда,
        когда она ответила согласием: в том же ходу, где показан
        разбор, инструмент откажет.
        """
        pending = self.pending_import
        if pending is None or pending.token != token:
            return (
                "Нечего заносить: сначала разбери выписку через "
                "preview_statement и покажи ей список."
            )
        if not pending.confirmed:
            return (
                "Разбор показан, но она ещё не ответила. Покажи ей "
                "список и дождись согласия — потом занесу."
            )

        await self._client.request(
            "POST", "/import/transactions", json={"items": pending.items}
        )
        self.pending_import = None
        tail = (
            f", пропущено дублей: {pending.duplicates}"
            if pending.duplicates
            else ""
        )
        return (
            f"Занесено операций: {len(pending.items)} "
            f"на счёт «{pending.account_name}»{tail}."
        )

    def arm_pending_import(self) -> None:
        """Разрешить запись разбора, показанного на прошлом ходу.

        Вызывается перед каждым прогоном агента, то есть после её
        сообщения. Так модель не может показать список и тут же его
        занести, не дав ей возразить.
        """
        if self.pending_import is not None:
            self.pending_import.confirmed = True

    async def _existing_keys(
        self, account_id: str, items: list[dict[str, Any]]
    ) -> set[tuple[str, Decimal]]:
        """Что по этому счёту уже записано в диапазоне выписки.

        Страницу API отдаёт не больше чем по сотне, поэтому читаем до
        конца: за месяц операций легко больше, а недочитанный хвост
        означал бы тихо задвоенные строки.
        """
        if not items:
            return set()
        dates = sorted(item["date"][:10] for item in items)
        params: dict[str, Any] = {
            "account_id": account_id,
            "date_from": dates[0],
            "date_to": dates[-1],
            "limit": _PAGE,
        }

        seen: set[tuple[str, Decimal]] = set()
        for _ in range(_MAX_PAGES):
            rows = await self._client.request(
                "GET", "/transactions", params=params
            )
            rows = rows or []
            seen.update(
                (str(row["date"])[:10], _norm_amount(str(row["amount"])))
                for row in rows
            )
            if len(rows) < _PAGE:
                break
            last = rows[-1]
            params = {
                **params,
                "cursor_date": last["date"],
                "cursor_id": last["id"],
            }
        return seen

    # --- настройка ------------------------------------------------

    async def set_budget(
        self,
        month: str,
        category_path: str,
        planned: str,
        notes: str | None = None,
        rollover: bool = False,
    ) -> str:
        """Задать план по категории на месяц (месяц в формате YYYY-MM).

        Если план по этой категории уже стоит — перезаписывает его.
        rollover — переносить ли неистраченный остаток на следующий
        месяц (для копилок вроде «на зимнюю резину»).
        """
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind="expense")
        category = find_category_by_path(paths, category_path)
        if category is None:
            return _unknown_category(category_path, paths)

        existing = await self._client.request(
            "GET", "/budgets", params={"month": month}
        )
        current = next(
            (
                row
                for row in existing or []
                if str(row.get("category_id")) == category.id
            ),
            None,
        )
        body: dict[str, Any] = {"planned": str(planned), "rollover": rollover}
        if notes:
            body["notes"] = notes

        if current is not None:
            await self._client.request(
                "PATCH", f"/budgets/{current['id']}", json=body
            )
            return f"План обновлён: {category.path} — {planned} за {month}."

        body |= {"month": month, "category_id": category.id}
        await self._client.request("POST", "/budgets", json=body)
        return f"План задан: {category.path} — {planned} за {month}."

    async def move_budget(
        self,
        month: str,
        from_category_path: str,
        to_category_path: str,
        amount: str,
    ) -> str:
        """Перенести часть плана из одной категории в другую.

        Третье правило ВНБ: перерасход закрывается не виной, а
        пересборкой плана. Сумма планов не меняется — деньги меняют
        назначение, операции и остатки счетов при этом не трогаются.
        Брать стоит из категории, где план ещё не исчерпан.
        """
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind="expense")
        source = find_category_by_path(paths, from_category_path)
        if source is None:
            return _unknown_category(from_category_path, paths)
        target = find_category_by_path(paths, to_category_path)
        if target is None:
            return _unknown_category(to_category_path, paths)

        await self._client.request(
            "POST",
            "/budgets/move",
            json={
                "month": month,
                "from_category_id": source.id,
                "to_category_id": target.id,
                "amount": str(amount),
            },
        )
        return (
            f"Перенесла {amount}: {source.path} → {target.path}, "
            f"месяц {month}."
        )

    async def create_category(
        self,
        name: str,
        kind: str = "expense",
        parent: str | None = None,
    ) -> str:
        """Завести категорию или подкатегорию.

        kind: expense или income. parent — название родительской
        категории, если это подкатегория. Заводи новую только когда
        существующая правда не подходит: лишние категории размывают
        отчёты сильнее, чем неточная классификация.
        """
        categories = await self._client.categories()
        body: dict[str, Any] = {"name": name, "kind": kind}
        if parent:
            paths = build_category_paths(categories, kind=kind)
            found = find_category_by_path(paths, parent)
            if found is None:
                return _unknown_category(parent, paths)
            body["parent_id"] = found.id

        await self._client.request("POST", "/categories", json=body)
        where = f" внутри «{parent}»" if parent else ""
        return f"Категория «{name}» заведена{where}."

    async def create_account(
        self,
        name: str,
        account_type: str,
        currency_code: str,
        initial_balance: str = "0",
    ) -> str:
        """Завести счёт.

        account_type: card (карта), cash (наличные), card_credit
        (кредитная карта), savings (накопительный), investment.
        initial_balance — остаток на момент заведения.
        """
        kind = account_type.strip().casefold()
        if kind not in _ACCOUNT_TYPES:
            return (
                f"Неизвестный тип счёта «{account_type}». "
                f"Доступные: {', '.join(sorted(_ACCOUNT_TYPES))}."
            )
        await self._client.request(
            "POST",
            "/accounts",
            json={
                "name": name,
                "type": kind,
                "currency_code": currency_code.strip().upper(),
                "initial_balance": str(initial_balance),
            },
        )
        return f"Счёт «{name}» заведён."

    async def create_credit(
        self,
        name: str,
        principal_initial: str,
        currency_code: str = "RUB",
        lender: str | None = None,
        annual_rate: str | None = None,
        term_months: int | None = None,
        monthly_payment: str | None = None,
        payment_day: int | None = None,
        start_date: str | None = None,
        account_name: str | None = None,
    ) -> str:
        """Завести кредит.

        principal_initial — сумма, которую выдал банк.
        account_name — счёт, с которого идут платежи.
        Ставка, срок, обязательный платёж и день платежа нужны, чтобы
        считать остаток срока: без них проекция графика не работает.
        """
        body: dict[str, Any] = {
            "name": name,
            "currency_code": currency_code.strip().upper(),
            "principal_initial": str(principal_initial),
        }
        if lender:
            body["lender"] = lender
        if annual_rate:
            body["annual_rate"] = str(annual_rate)
        if term_months:
            body["term_months"] = term_months
        if monthly_payment:
            body["monthly_payment"] = str(monthly_payment)
        if payment_day:
            body["payment_day"] = payment_day
        if start_date:
            body["start_date"] = start_date
        if account_name:
            accounts = await self._client.accounts()
            account = _find_account(accounts, account_name)
            if account is None:
                names = ", ".join(a.name for a in accounts)
                return f"Счёт не найден. Доступные: {names}"
            body["linked_account_id"] = account.id

        await self._client.request("POST", "/credits", json=body)
        return f"Кредит «{name}» заведён."

    async def add_recurring(
        self,
        name: str,
        category_path: str,
        monthly_amount: str,
        currency_code: str = "RUB",
        required: str = "required",
        comments: str | None = None,
    ) -> str:
        """Добавить строку в план-минимум — то, что платится каждый месяц.

        required: required (без этого не прожить: аренда, связь) или
        optional (можно урезать). План-минимум резервируется при
        расчёте дневного лимита, поэтому сюда идут только реально
        обязательные ежемесячные траты.
        """
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind="expense")
        category = find_category_by_path(paths, category_path)
        if category is None:
            return _unknown_category(category_path, paths)

        body: dict[str, Any] = {
            "name": name,
            "category_id": category.id,
            "monthly_amount": str(monthly_amount),
            "currency_code": currency_code.strip().upper(),
            "required": required,
        }
        if comments:
            body["comments"] = comments

        await self._client.request("POST", "/recurring", json=body)
        return f"В план-минимум добавлено: {name} — {monthly_amount}."

    async def delete_credit_payment(
        self, credit_id: str, payment_id: str
    ) -> str:
        """Удалить платёж по кредиту.

        Возвращает погашенное тело обратно в долг — этим платёж и
        отличается от обычной операции. Нужно, когда платёж задвоился:
        например, внесён руками и повторно приехал с выпиской.

        Действие необратимо, поэтому спроси подтверждение у неё
        прежде, чем вызывать, и назови сумму и дату.
        """
        await self._client.request(
            "DELETE", f"/credits/{credit_id}/payments/{payment_id}"
        )
        return "Платёж удалён, тело кредита возвращено в долг."

    async def list_credit_payments(self, credit_id: str) -> str:
        """Платежи по кредиту — чтобы найти нужный перед удалением."""
        return str(
            await self._client.request("GET", f"/credits/{credit_id}/payments")
        )

    async def archive_account(
        self, account_name: str, force: bool = False
    ) -> str:
        """Убрать счёт из активных.

        Архивный счёт не входит в капитал. Со счёта с остатком итог
        изменится на всю сумму остатка, поэтому такой архивируется
        только с force=True — и ставить его можно лишь после того,
        как она подтвердила это в переписке.
        """
        accounts = await self._client.accounts()
        account = _find_account(accounts, account_name)
        if account is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"

        params = {"force": "true"} if force else {}
        await self._client.request(
            "DELETE", f"/accounts/{account.id}", params=params
        )
        return f"Счёт «{account.name}» убран в архив."

    async def update_recurring(
        self,
        name: str,
        monthly_amount: str | None = None,
        category_path: str | None = None,
        new_name: str | None = None,
        required: str | None = None,
    ) -> str:
        """Поправить строку плана-минимума.

        Ищет строку по названию. Меняются только переданные поля.
        Именно правка, а не добавление: две строки на одну и ту же
        трату завышают резерв и занижают дневной лимит.
        """
        found, error = await self._find_recurring(name)
        if found is None:
            return error

        body: dict[str, Any] = {}
        if monthly_amount:
            body["monthly_amount"] = str(monthly_amount)
        if new_name:
            body["name"] = new_name
        if required:
            body["required"] = required
        if category_path:
            categories = await self._client.categories()
            paths = build_category_paths(categories, kind="expense")
            category = find_category_by_path(paths, category_path)
            if category is None:
                return _unknown_category(category_path, paths)
            body["category_id"] = category.id
        if not body:
            return "Нечего менять: не передано ни одно поле."

        await self._client.request(
            "PATCH", f"/recurring/{found['id']}", json=body
        )
        return f"Строка «{found['name']}» обновлена."

    async def delete_recurring(self, name: str) -> str:
        """Убрать строку из плана-минимума.

        Нужно, когда трата больше не повторяется или когда общая
        строка заменена подробными: «Связь» на «МТС» и «Йота».
        Действие меняет дневной лимит, поэтому спроси согласия
        прежде, чем вызывать.
        """
        found, error = await self._find_recurring(name)
        if found is None:
            return error
        await self._client.request("DELETE", f"/recurring/{found['id']}")
        return f"Строка «{found['name']}» убрана из плана-минимума."

    async def _find_recurring(
        self, name: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Найти строку плана по названию: точное, затем однозначное.

        Неоднозначное совпадение не разрешаем: у неё есть «Интернет»
        и «Стационарный интернет», и молча взять первый попавшийся
        значит поправить не ту строку.
        """
        rows = await self._client.request("GET", "/recurring") or []
        live = [r for r in rows if not r.get("is_archived")]
        needle = name.casefold().strip()

        exact = [r for r in live if str(r["name"]).casefold() == needle]
        if len(exact) == 1:
            return exact[0], ""

        partial = [r for r in live if needle in str(r["name"]).casefold()]
        if len(partial) == 1:
            return partial[0], ""
        if len(partial) > 1:
            names = ", ".join(f"«{r['name']}»" for r in partial)
            return None, (
                f"Под «{name}» подходит несколько строк: {names}. "
                "Уточни, какую именно."
            )

        names = ", ".join(f"«{r['name']}»" for r in live) or "список пуст"
        return None, f"Строка «{name}» не найдена. Есть: {names}"

    async def delete_transfer(self, transfer_id: str) -> str:
        """Удалить перевод между счетами целиком.

        У перевода две ноги — списание и зачисление. Удалять их по
        отдельности нельзя, иначе деньги повиснут на одном счёте.
        transfer_id виден в поле transfer_id любой из ног, его даёт
        list_transactions.
        """
        await self._client.request("DELETE", f"/transfers/{transfer_id}")
        return "Перевод удалён целиком, обе ноги."

    async def update_account(
        self,
        name: str,
        new_name: str | None = None,
        account_type: str | None = None,
        color: str | None = None,
        comments: str | None = None,
    ) -> str:
        """Переименовать счёт или сменить его тип и цвет.

        Начальный баланс здесь не меняется: после появления операций
        он заблокирован, и исправлять остаток нужно операцией, а не
        правкой прошлого.
        """
        accounts = await self._client.accounts()
        account = _find_account(accounts, name)
        if account is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"

        body: dict[str, Any] = {}
        if new_name:
            body["name"] = new_name
        if account_type:
            if account_type not in _ACCOUNT_TYPES:
                return f"Тип счёта должен быть одним из: {_ACCOUNT_TYPES}."
            body["type"] = account_type
        if color:
            body["color"] = color
        if comments is not None:
            body["comments"] = comments
        if not body:
            return "Нечего менять: не передано ни одно поле."

        await self._client.request(
            "PATCH", f"/accounts/{account.id}", json=body
        )
        return f"Счёт «{account.name}» обновлён."

    async def restore_account(self, name: str) -> str:
        """Вернуть счёт из архива в активные."""
        rows = await self._client.request("GET", "/accounts") or []
        archived = [
            r
            for r in rows
            if r.get("is_archived")
            and name.casefold() in str(r["name"]).casefold()
        ]
        if len(archived) != 1:
            names = ", ".join(
                f"«{r['name']}»" for r in rows if r.get("is_archived")
            )
            return f"Не нашла один архивный счёт по «{name}». Есть: {names}"

        await self._client.request(
            "POST", f"/accounts/{archived[0]['id']}/restore"
        )
        return f"Счёт «{archived[0]['name']}» возвращён из архива."

    async def update_category(
        self, path: str, new_name: str, kind: str = "expense"
    ) -> str:
        """Переименовать категорию. Путь вида «Еда → Кофейни»."""
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind=kind)
        found = find_category_by_path(paths, path)
        if found is None:
            return _unknown_category(path, paths)

        await self._client.request(
            "PATCH", f"/categories/{found.id}", json={"name": new_name}
        )
        return f"Категория «{found.path}» переименована в «{new_name}»."

    async def archive_category(self, path: str, kind: str = "expense") -> str:
        """Убрать категорию в архив.

        Прошлые операции сохраняют её имя снимком, так что история не
        портится. Спроси согласия прежде, чем вызывать.
        """
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind=kind)
        found = find_category_by_path(paths, path)
        if found is None:
            return _unknown_category(path, paths)

        await self._client.request("DELETE", f"/categories/{found.id}")
        return f"Категория «{found.path}» убрана в архив."

    async def update_credit(
        self,
        name: str,
        annual_rate: str | None = None,
        term_months: str | None = None,
        monthly_payment: str | None = None,
        payment_day: str | None = None,
        new_name: str | None = None,
    ) -> str:
        """Поправить условия кредита: ставку, срок, платёж, день.

        Остаток долга здесь не меняется — он считается по платежам.
        Если долг разошёлся с банком, ищи лишний или недостающий
        платёж, а не правь итог.
        """
        found, error = await self._find_credit(name)
        if found is None:
            return error

        body: dict[str, Any] = {}
        if annual_rate:
            body["annual_rate"] = str(annual_rate)
        if term_months:
            body["term_months"] = int(term_months)
        if monthly_payment:
            body["monthly_payment"] = str(monthly_payment)
        if payment_day:
            body["payment_day"] = int(payment_day)
        if new_name:
            body["name"] = new_name
        if not body:
            return "Нечего менять: не передано ни одно поле."

        await self._client.request(
            "PATCH", f"/credits/{found['id']}", json=body
        )
        return f"Кредит «{found['name']}» обновлён."

    async def archive_credit(self, name: str) -> str:
        """Убрать кредит в архив — когда он закрыт.

        Архивный кредит перестаёт вычитаться из капитала. Спроси
        согласия прежде, чем вызывать.
        """
        found, error = await self._find_credit(name)
        if found is None:
            return error
        await self._client.request("DELETE", f"/credits/{found['id']}")
        return f"Кредит «{found['name']}» убран в архив."

    async def delete_budget(self, month: str, category_path: str) -> str:
        """Убрать план по категории на месяц (месяц в формате YYYY-MM).

        Не то же самое, что поставить ноль: план исчезает совсем, и
        категория перестаёт участвовать в распределении.
        """
        categories = await self._client.categories()
        paths = build_category_paths(categories, kind="expense")
        category = find_category_by_path(paths, category_path)
        if category is None:
            return _unknown_category(category_path, paths)

        rows = (
            await self._client.request(
                "GET", "/budgets", params={"month": month}
            )
            or []
        )
        match = [r for r in rows if r.get("category_id") == category.id]
        if not match:
            return f"На {month} плана по «{category.path}» нет."

        await self._client.request("DELETE", f"/budgets/{match[0]['id']}")
        return f"План по «{category.path}» на {month} убран."

    async def _find_credit(
        self, name: str
    ) -> tuple[dict[str, Any] | None, str]:
        """Найти кредит по названию: точное, затем однозначное."""
        rows = await self._client.request("GET", "/credits") or []
        needle = name.casefold().strip()

        exact = [r for r in rows if str(r["name"]).casefold() == needle]
        if len(exact) == 1:
            return exact[0], ""
        partial = [r for r in rows if needle in str(r["name"]).casefold()]
        if len(partial) == 1:
            return partial[0], ""
        if len(partial) > 1:
            names = ", ".join(f"«{r['name']}»" for r in partial)
            return None, (
                f"Под «{name}» подходит несколько кредитов: {names}. "
                "Уточни, какой именно."
            )
        names = ", ".join(f"«{r['name']}»" for r in rows) or "список пуст"
        return None, f"Кредит «{name}» не найден. Есть: {names}"

    # --- чтение ---------------------------------------------------

    async def get_daily_allowance(self, until: str | None = None) -> str:
        """Сколько можно тратить в день, не сорвав обязательства.

        Из денег на счетах вычитается неоплаченный план-минимум и
        платежи по кредитам, которые наступят до горизонта, и только
        остаток делится на оставшиеся дни. until — дата горизонта в
        формате YYYY-MM-DD; по умолчанию конец текущего месяца.
        """
        params = {"until": until} if until else None
        return str(
            await self._client.request(
                "GET", "/summary/daily-allowance", params=params
            )
        )

    async def list_recurring(self) -> str:
        """План-минимум: обязательные ежемесячные траты."""
        return str(await self._client.request("GET", "/recurring"))

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


def _row_label(row: StatementRow) -> str:
    """Строка разбора так, как её увидит человек в переписке."""
    sign = "−" if row.kind == "expense" else "+"
    day = row.date[:10]
    tail = f" · {row.comment}" if row.comment else ""
    return f"{day} · {sign}{row.amount} · {row.category_path}{tail}"


def _norm_amount(value: str) -> Decimal:
    """Сравнивать суммы как числа: «300» и «300.0000» — одно и то же."""
    try:
        return abs(Decimal(value))
    except InvalidOperation:
        return Decimal(0)
