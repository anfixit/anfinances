"""Набор инструментов бота, дополненный для внешних ассистентов.

Основа — тот же ``ToolBox``, что у телеграм-бота: те же разрешение
счетов и категорий по названию, тот же разбор выписки, те же тексты
для модели. Здесь добавлено то, чего у бота нет или что в MCP
работает иначе.

Импорт выписки. У бота разбор и запись разведены по ходам беседы:
занести можно только после её следующего сообщения. В MCP ходов нет,
есть только вызовы. Поэтому ``preview_statement`` возвращает
``preview_id`` — отпечаток именно показанных строк, а
``import_statement`` без него не пишет. Согласие человека даёт сам
клиент: ChatGPT и Claude спрашивают подтверждение перед каждым
пишущим инструментом. Отпечаток гарантирует, что занесено будет
ровно то, что показали: изменился разбор — изменился и id, и старый
перестаёт подходить.
"""

import asyncio
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from anfinances_bot.agent.tools import (
    PendingImport,
    StatementRow,
    ToolBox,
    _find_account,
)

__all__ = ["McpToolBox", "preview_id_of"]


def preview_id_of(pending: PendingImport) -> str:
    """Короткий отпечаток разбора: счёт плюс все показанные строки."""
    raw = json.dumps(
        [pending.account_id, [list(row) for row in pending.fingerprint]],
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class McpToolBox(ToolBox):
    # --- выписка --------------------------------------------------

    async def mcp_preview_statement(
        self, account_name: str, rows: list[StatementRow]
    ) -> str:
        """Разобрать банковскую выписку и показать, что будет занесено.

        Ничего не записывает. Сверяет строки с уже записанным по этому
        счёту и возвращает только новые операции, число пропущенных
        дублей и preview_id. Все строки — по одному счёту.

        payee заполняй только для организаций («Пятёрочка», «Яндекс Go»),
        не номером платёжного поручения и не словами из назначения
        («СБП»). Перевод человеку — payee пустой, имя в описание
        строки. По знакомой организации категорию подставит сам сайт.
        category_path всё равно проставляй — он нужен для незнакомых.

        Покажи список пользователю целиком. Заносит его
        import_statement с этим preview_id — и только после того, как
        пользователь согласился.
        """
        before = dict(self.pending_imports)
        text = await self.preview_statement(account_name, rows)
        fresh = [
            pending
            for account_id, pending in self.pending_imports.items()
            if before.get(account_id) is not pending
        ]
        if not fresh:
            # Разбор не удался или заносить нечего — текст уже
            # объясняет почему, id выдавать не к чему.
            return text
        preview_id = preview_id_of(fresh[0])
        # Хвост бота про «её ответ на следующем ходу» здесь неверен:
        # меняем его на инструкцию с preview_id.
        head = text.split("\n\nПокажи этот список", 1)[0]
        return (
            f"{head}\n\npreview_id: {preview_id}\n"
            "Покажи этот список пользователю и спроси, заносить ли. "
            "Когда он согласится — вызови import_statement с этим "
            "preview_id; разбирать заново не нужно."
        )

    async def mcp_import_statement(self, preview_id: str) -> str:
        """Занести разобранную выписку, которую пользователь одобрил.

        preview_id — из ответа preview_statement. Заносится ровно
        показанный список: если выписку разбирали заново и строки
        изменились, старый preview_id уже не подойдёт — покажи новый
        разбор и спроси снова. Повторный вызов с тем же preview_id
        ничего не задвоит: после записи разбор забывается.
        """
        wanted = preview_id.strip()
        match = [
            p
            for p in self.pending_imports.values()
            if preview_id_of(p) == wanted
        ]
        if not match:
            waiting = ", ".join(
                f"«{p.account_name}» ({preview_id_of(p)})"
                for p in self.pending_imports.values()
            )
            hint = f" Ждут записи: {waiting}." if waiting else ""
            return (
                f"Разбора с preview_id {wanted} нет: он уже занесён, "
                "устарел или выписку разобрали заново." + hint
            )
        pending = match[0]
        # Согласие дал клиент, подтвердив вызов, — отмечаем только
        # этот разбор. Остальные счета ждут своего preview_id.
        pending.confirmed = True
        return await self.import_statement(account_name=pending.account_name)

    # --- переводы -------------------------------------------------

    async def update_transfer(
        self,
        transfer_id: str,
        when: str | None = None,
        amount_from: str | None = None,
        amount_to: str | None = None,
        from_account_name: str | None = None,
        to_account_name: str | None = None,
        fee_amount: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Исправить перевод между своими счетами: дату, суммы, счета.

        Меняются только переданные поля, остальное остаётся как было.
        Обе ноги перевода правятся вместе, поэтому ошибку в дате или
        сумме исправляй здесь, а не новым переводом — иначе он
        задвоится. transfer_id — поле transfer_id у любой из ног в
        list_transactions.

        Если валюты счетов совпадают, достаточно одной суммы — вторая
        станет такой же. Если разные — нужны обе: они фиксируют
        фактический курс. fee_amount — комиссия; "0" её убирает.
        """
        current = await self._client.request(
            "GET", f"/transfers/{transfer_id}"
        )
        legs = (current or {}).get("legs") or []
        source = next((x for x in legs if _num(x["amount"]) < 0), None)
        target = next((x for x in legs if _num(x["amount"]) > 0), None)
        if source is None or target is None:
            return f"Перевод {transfer_id} не найден или повреждён."

        body: dict[str, Any] = {
            "from_account_id": source["account_id"],
            "to_account_id": target["account_id"],
            "amount_from": str(-_num(source["amount"])),
            "amount_to": str(_num(target["amount"])),
            "date": source["date"],
            "comment": source.get("comment"),
        }
        fee = (current or {}).get("fee")
        if fee:
            body["fee_amount"] = str(abs(_num(fee["amount"])))
            body["fee_category_id"] = fee.get("category_id")

        names = {
            "from_account_id": from_account_name,
            "to_account_id": to_account_name,
        }
        if any(names.values()):
            accounts = await self._client.accounts()
            for field, name in names.items():
                if not name:
                    continue
                account = _find_account(accounts, name)
                if account is None:
                    available = ", ".join(a.name for a in accounts)
                    return f"Счёт «{name}» не найден. Доступные: {available}"
                body[field] = account.id

        if amount_from or amount_to:
            moving = any(names.values())
            currencies = {source.get("currency_code")}
            currencies.add(target.get("currency_code"))
            one_amount = not (amount_from and amount_to)
            if one_amount and (moving or len(currencies) > 1):
                return (
                    "Нужны обе суммы: сколько ушло и сколько пришло. "
                    "Валюты счетов разные или счета меняются — "
                    "спроси у пользователя вторую сумму."
                )
            try:
                sent = _num(amount_from or amount_to)
                received = _num(amount_to or amount_from)
            except InvalidOperation:
                return "Суммы должны быть числами."
            body["amount_from"] = str(sent)
            body["amount_to"] = str(received)
        if when:
            moment = self._strict_moment(when)
            if moment is None:
                return f"Не понимаю дату «{when}». Нужен формат YYYY-MM-DD."
            body["date"] = moment
        if comment is not None:
            body["comment"] = comment
        if fee_amount is not None:
            try:
                fee_value = _num(fee_amount)
            except InvalidOperation:
                return "Комиссия должна быть числом."
            if fee_value:
                body["fee_amount"] = str(fee_value)
            else:
                body.pop("fee_amount", None)
                body.pop("fee_category_id", None)

        await self._client.request(
            "PATCH", f"/transfers/{transfer_id}", json=body
        )
        return (
            f"Перевод исправлен: {body['amount_from']} → "
            f"{body['amount_to']}, дата {body['date']}."
        )

    # --- архив ----------------------------------------------------
    #
    # У бота архив — те же методы без confirm: там согласие видно в
    # переписке. В MCP подтверждение клиента общее для всех пишущих
    # вызовов, поэтому архиву нужен свой явный флаг.

    async def mcp_archive_account(
        self, account_name: str, confirm: bool = False
    ) -> str:
        """Убрать в архив счёт, который больше не нужен.

        Только пустой счёт: архивный не входит в капитал, и деньги с
        него молча пропали бы из итога. Если остаток не ноль — сначала
        переведи его на другой счёт. Счёт с остатком архивирует только
        сам пользователь, на сайте.

        Сначала назови пользователю счёт и спроси, убирать ли его в
        архив. confirm=true — только после его прямого согласия в
        этом разговоре. Вернуть счёт — restore_account.
        """
        if not confirm:
            return _ask_first(f"счёт «{account_name}»")
        accounts = await self._client.accounts()
        account = _find_account(accounts, account_name)
        if account is None:
            names = ", ".join(a.name for a in accounts)
            return f"Счёт не найден. Доступные: {names}"
        balance = account.current_balance
        if balance is not None and balance != 0:
            return (
                f"На счёте «{account.name}» остаток {balance} "
                f"{account.currency_code}. Архивировать можно только "
                "пустой счёт: сначала переведи остаток. Счёт с "
                "остатком архивирует сам пользователь на сайте."
            )
        await self._client.request("DELETE", f"/accounts/{account.id}")
        return (
            f"Счёт «{account.name}» убран в архив. Вернуть его — "
            "restore_account с этим названием."
        )

    async def mcp_archive_credit(
        self, name: str, confirm: bool = False
    ) -> str:
        """Убрать в архив погашенный кредит.

        Только кредит без долга: архивный не вычитается из капитала, и
        долг молча пропал бы из итога. Если долг остался, а банк
        считает кредит закрытым, — не хватает платежа или разбивка
        неверна: запиши последний платёж (create_credit_payment) или
        разберись с пользователем, но не архивируй.

        Сначала назови пользователю кредит и спроси, убирать ли его в
        архив. confirm=true — только после его прямого согласия в
        этом разговоре. Вернуть кредит — restore_credit.
        """
        if not confirm:
            return _ask_first(f"кредит «{name}»")
        found, error = await self._find_credit(name)
        if found is None:
            return error
        try:
            debt = _num(found.get("principal_balance", "0"))
        except InvalidOperation:
            debt = Decimal(0)
        if debt > 0:
            return (
                f"По кредиту «{found['name']}» остаток долга {debt} "
                f"{found.get('currency_code', '')}. Архивировать можно "
                "только погашенный кредит: сначала запиши последний "
                "платёж."
            )
        await self._client.request("DELETE", f"/credits/{found['id']}")
        return (
            f"Кредит «{found['name']}» (id {found['id']}) убран в "
            "архив. Вернуть его — restore_credit с этим названием."
        )

    async def restore_credit(self, name: str) -> str:
        """Вернуть кредит из архива в активные."""
        rows = (
            await self._client.request(
                "GET", "/credits", params={"include_archived": "true"}
            )
            or []
        )
        archived = [r for r in rows if r.get("is_archived")]
        needle = name.casefold().strip()
        exact = [r for r in archived if str(r["name"]).casefold() == needle]
        match = exact or [
            r for r in archived if needle in str(r["name"]).casefold()
        ]
        if len(match) != 1:
            names = ", ".join(f"«{r['name']}»" for r in archived)
            return (
                f"Не нашла один архивный кредит по «{name}». "
                f"В архиве: {names or 'пусто'}"
            )
        await self._client.request(
            "POST", f"/credits/{match[0]['id']}/restore"
        )
        return f"Кредит «{match[0]['name']}» возвращён из архива."

    # --- удаление в корзину ---------------------------------------
    #
    # Удалённое не пропадает: сайт кладёт копию в корзину, откуда
    # restore_deleted возвращает её с теми же id. Поэтому удаление
    # открыто, но, как и архив, только с явным confirm.

    async def mcp_delete_transaction(
        self, transaction_id: str, confirm: bool = False
    ) -> str:
        """Удалить ошибочную операцию — например, задвоенную покупку.

        Трата, доход, возврат, кредит, корректировка. Переводы —
        delete_transfer, платежи по кредиту — delete_credit_payment.
        Если операцию надо поправить, а не убрать, — update_transaction.

        Копия ляжет в корзину; вернуть — restore_deleted. Сверенную с
        банком операцию удалить нельзя: это решает пользователь на
        сайте.

        Сначала назови пользователю операцию — сумму, дату, счёт — и
        спроси, удалять ли. confirm=true — только после его прямого
        согласия в этом разговоре.
        """
        if not confirm:
            return _ask_delete("операцию")
        data = await self._client.request(
            "DELETE", f"/transactions/{transaction_id}"
        )
        return _deleted(data)

    async def mcp_delete_transfer(
        self, transfer_id: str, confirm: bool = False
    ) -> str:
        """Удалить перевод между своими счетами целиком — обе ноги.

        Нужно, когда перевод задвоился. Если неверны дата или сумма —
        не удаляй, а исправь: update_transfer. transfer_id — поле
        transfer_id у любой из ног в list_transactions.

        Копия ляжет в корзину; вернуть — restore_deleted. Сначала
        назови пользователю перевод и спроси, удалять ли; confirm=true
        — только после его прямого согласия.
        """
        if not confirm:
            return _ask_delete("перевод")
        data = await self._client.request(
            "DELETE", f"/transfers/{transfer_id}"
        )
        return _deleted(data)

    async def mcp_delete_credit_payment(
        self, credit_id: str, payment_id: str, confirm: bool = False
    ) -> str:
        """Удалить платёж по кредиту — например, задвоенный.

        Погашенное этим платежом тело вернётся в долг, а списание
        исчезнет со счёта. payment_id — из list_credit_payments.

        Копия ляжет в корзину; вернуть — restore_deleted, и тогда тело
        снова погасится. Сначала назови пользователю платёж — сумму и
        дату — и спроси, удалять ли; confirm=true — только после его
        прямого согласия.
        """
        if not confirm:
            return _ask_delete("платёж по кредиту")
        data = await self._client.request(
            "DELETE", f"/credits/{credit_id}/payments/{payment_id}"
        )
        return _deleted(data)

    async def list_deleted(self, limit: int = 20) -> str:
        """Корзина: что удалено, кем и когда, свежее сверху.

        id каждой строки — для restore_deleted. Уже возвращённое здесь
        не показывается.
        """
        rows = (
            await self._client.request(
                "GET", "/trash", params={"limit": limit}
            )
            or []
        )
        if not rows:
            return "Корзина пуста."
        return "\n".join(
            f"{r['id']} · {str(r['deleted_at'])[:10]} · {r['source']} · "
            f"{r['summary']}"
            for r in rows
        )

    async def restore_deleted(self, trash_id: str) -> str:
        """Вернуть из корзины удалённую операцию, перевод или платёж.

        Возвращается ровно то, что было, с теми же id. Платёж по
        кредиту при возврате снова гасит тело. trash_id — из ответа
        удаления или из list_deleted.
        """
        data = await self._client.request("POST", f"/trash/{trash_id}/restore")
        return f"Возвращено: {(data or {}).get('summary', trash_id)}."

    # --- аналитика ------------------------------------------------

    async def get_income_by_category(self, month: str) -> str:
        """Доходы по категориям за месяц в формате YYYY-MM.

        Зеркало get_by_category для доходного дерева: откуда пришли
        деньги — зарплата, подработки, кэшбэк. Возвраты и получение
        кредита сюда не входят.
        """
        return _as_json(
            await self._client.request(
                "GET", "/summary/income-by-category", params={"month": month}
            )
        )

    async def get_upcoming_payments(self, days: int = 30) -> str:
        """Платежи, которые наступят в ближайшие дни.

        Кредиты и строки плана-минимума с датами — чтобы заранее
        видеть, сколько денег уйдёт и когда. days — горизонт в днях,
        по умолчанию 30.
        """
        return _as_json(
            await self._client.request(
                "GET", "/summary/upcoming-payments", params={"days": days}
            )
        )

    async def get_payoff_plan(
        self,
        strategy: Literal["avalanche", "snowball"] = "avalanche",
        extra_monthly: str = "0",
    ) -> str:
        """План досрочного погашения кредитов.

        strategy: avalanche — сначала самый дорогой по ставке (меньше
        переплата), snowball — сначала самый маленький по остатку
        (быстрее закрываются кредиты). extra_monthly — сколько сверх
        обязательных платежей можно отдавать в месяц, числом.
        """
        try:
            extra = Decimal(str(extra_monthly).replace(",", "."))
        except InvalidOperation:
            return "extra_monthly должен быть числом, например 5000."
        return _as_json(
            await self._client.request(
                "GET",
                "/credits/payoff-plan",
                params={"strategy": strategy, "extra_monthly": str(extra)},
            )
        )

    async def get_financial_overview(self) -> str:
        """Короткая сводка финансов: капитал, дневной лимит, возраст денег.

        Один вызов вместо трёх: остатки по счетам и долг по
        кредитам, сколько можно тратить в день с учётом обязательств,
        и покрыты ли траты месяца доходом прошлого. Начинай с него,
        когда спрашивают «как у меня дела с деньгами».
        """
        dashboard, allowance, age = await asyncio.gather(
            self._client.request("GET", "/summary/dashboard"),
            self._client.request("GET", "/summary/daily-allowance"),
            self._client.request("GET", "/summary/money-age"),
        )
        return "\n".join(
            [
                *_dashboard_lines(dashboard or {}),
                "",
                *_allowance_lines(allowance or {}),
                "",
                *_age_lines(age or {}),
            ]
        )


def _ask_first(what: str) -> str:
    return (
        f"Ничего не сделано: убрать в архив {what} можно только с "
        "прямого согласия пользователя. Спроси его и, если он "
        "согласится, вызови снова с confirm=true."
    )


def _ask_delete(what: str) -> str:
    return (
        f"Ничего не сделано: удалить {what} можно только с прямого "
        "согласия пользователя. Назови, что именно удаляешь, спроси его "
        "и, если он согласится, вызови снова с confirm=true."
    )


def _deleted(data: Any) -> str:
    data = data or {}
    return (
        f"Удалено в корзину: {data.get('summary', '')}. "
        f"Вернуть — restore_deleted с trash_id {data.get('trash_id')}."
    )


def _num(value: Any) -> Decimal:
    """Сумма из ответа сайта или от модели — Decimal, запятая как точка."""
    return Decimal(str(value).strip().replace(",", "."))


def _as_json(data: Any) -> str:
    """Ответ сайта — компактным JSON: модели его читать проще str()."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _missing(data: dict[str, Any]) -> str:
    """Предупреждение, если итог неполный из-за курсов."""
    if data.get("is_total_complete", True):
        return ""
    codes = ", ".join(data.get("missing_rate_currencies") or [])
    return f" (без курса: {codes} — итог неполный)"


def _dashboard_lines(data: dict[str, Any]) -> list[str]:
    lines = [
        f"Капитал: {data.get('total_capital_rub')} ₽{_missing(data)}",
        f"Долг по кредитам: {data.get('total_credit_debt_rub')} ₽",
        "Счета:",
    ]
    for row in data.get("accounts") or []:
        rub = row.get("balance_rub")
        in_rub = (
            f" (≈{rub} ₽)"
            if rub is not None and row.get("currency_code") != "RUB"
            else ""
        )
        lines.append(
            f"  {row.get('name')}: {row.get('balance')} "
            f"{row.get('currency_code')}{in_rub}"
        )
    return lines


def _allowance_lines(data: dict[str, Any]) -> list[str]:
    lines = [
        f"Можно тратить в день: {data.get('per_day_rub')} ₽ "
        f"до {data.get('until')} (дней: {data.get('days_left')})",
        f"Свободные деньги: {data.get('liquid_rub')} ₽, "
        f"обязательства до горизонта: {data.get('obligations_rub')} ₽, "
        f"безопасно потратить: {data.get('safe_to_spend_rub')} ₽",
        f"Не распределено по планам: {data.get('unallocated_rub')} ₽",
    ]
    if data.get("is_short"):
        lines.append("Обязательств больше, чем денег на счетах.")
    if data.get("is_overplanned"):
        lines.append("Распланировано больше, чем есть на счетах.")
    return lines


def _age_lines(data: dict[str, Any]) -> list[str]:
    coverage = data.get("coverage")
    if coverage is None:
        head = f"Трат в {data.get('current_month')} ещё не было."
    else:
        verdict = "покрыты" if data.get("is_covered") else "не покрыты"
        head = (
            f"Траты {data.get('current_month')} {verdict} доходом "
            f"{data.get('previous_month')}: доход "
            f"{data.get('previous_month_income_rub')} ₽, траты "
            f"{data.get('current_month_expense_rub')} ₽, покрытие "
            f"{coverage}"
        )
    age = data.get("age_days")
    tail = f" Возраст денег: {age} дн." if age is not None else ""
    return [head + tail]
