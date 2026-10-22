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

from anfinances_bot.agent.tools import PendingImport, StatementRow, ToolBox

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

        В каждой строке заполняй payee — кому платили («Пятёрочка»,
        «Яндекс Go»), а не номер платёжного поручения: по знакомому
        получателю категорию подставит сам сайт. category_path всё
        равно проставляй — он нужен для незнакомых.

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
