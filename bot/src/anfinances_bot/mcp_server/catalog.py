"""Какие инструменты бота видны внешним ассистентам и как.

Список закрытый: в MCP попадает только то, что перечислено здесь.
Удаления и архивации нет вовсе — ни операций, ни счетов, ни
категорий. Ассистент в чужом приложении ошибается так же, как
телеграм-бот, но отменить за ним нечем: истории правок у сайта нет.
Правка справочников (счета, категории, кредиты, получатели) тоже не
нужна для ежедневной работы и остаётся сайту и боту.

Чтение доступно любому токену подключения. Запись — только токену
с ``finance.write``; без него пишущие инструменты не показываются в
списке и не выполняются, даже если клиент вызовет их по имени.
"""

import copy
from dataclasses import dataclass
from typing import Any

import mcp_types as types
from anthropic import beta_async_tool
from anthropic.lib.tools import BetaAsyncFunctionTool

from anfinances_bot.agent.tools import compact_schema
from anfinances_bot.mcp_server.config import READ_SCOPE, WRITE_SCOPE
from anfinances_bot.mcp_server.toolbox import McpToolBox

__all__ = [
    "BY_NAME",
    "CATALOG",
    "IDEMPOTENCY_ARG",
    "ToolSpec",
    "bind",
    "describe",
]

IDEMPOTENCY_ARG = "idempotency_key"

_IDEMPOTENCY_SCHEMA = {
    "type": "string",
    "description": (
        "Необязательный ключ повтора. Повторный вызов с тем же ключом "
        "в течение суток ничего не запишет второй раз и вернёт первый "
        "ответ. Ставь, если повторяешь вызов после обрыва связи."
    ),
}


@dataclass(frozen=True)
class ToolSpec:
    """Один инструмент MCP поверх метода ``McpToolBox``."""

    name: str
    method: str
    title: str
    # Какое право нужно на вызов. Не всегда совпадает с read_only:
    # сверка счёта ничего не меняет, но ходит в сайт POST-запросом,
    # а токену на чтение сайт разрешает только GET.
    scope: str = READ_SCOPE
    read_only: bool = True
    idempotency: bool = False
    # Если описание бота не годится вне телеграма.
    description: str | None = None

    @property
    def writes(self) -> bool:
        return self.scope == WRITE_SCOPE


def _read(name: str, title: str, **kw: Any) -> ToolSpec:
    return ToolSpec(
        name=name, method=kw.pop("method", name), title=title, **kw
    )


def _write(name: str, title: str, **kw: Any) -> ToolSpec:
    return ToolSpec(
        name=name,
        method=kw.pop("method", name),
        title=title,
        scope=WRITE_SCOPE,
        read_only=False,
        **kw,
    )


CATALOG: tuple[ToolSpec, ...] = (
    # --- чтение ---
    _read("get_financial_overview", "Сводка финансов"),
    _read("list_accounts", "Счета и остатки"),
    _read("get_capital", "Капитал и долг"),
    _read("get_daily_allowance", "Дневной лимит"),
    _read("get_money_age", "Возраст денег"),
    _read("list_transactions", "Последние операции"),
    _read("list_uncategorized", "Операции без категории"),
    _read("list_categories", "Дерево категорий"),
    _read("get_by_category", "Расходы по категориям"),
    _read("get_income_by_category", "Доходы по категориям"),
    _read("get_budget", "Бюджет месяца"),
    _read("list_goals", "Цели накопления"),
    _read("list_recurring", "План-минимум"),
    _read("get_upcoming_payments", "Ближайшие платежи"),
    _read("get_credits", "Кредиты"),
    _read("get_credit_projection", "Прогноз по кредиту"),
    _read(
        "list_credit_payments",
        "Платежи по кредиту",
        description="Платежи по кредиту: дата, сумма, тело и проценты.",
    ),
    _read("get_payoff_plan", "План погашения кредитов"),
    _read("list_payees", "Получатели"),
    _read("list_new_payees", "Новые получатели"),
    _read("get_by_payee", "Траты по получателям"),
    _read("get_method_reference", "Справочник по методу ВНБ"),
    _read(
        "check_account_balance",
        "Сверка счёта с банком",
        scope=WRITE_SCOPE,
    ),
    # --- запись ---
    _write("create_expense", "Записать трату", idempotency=True),
    _write("create_income", "Записать доход", idempotency=True),
    _write("create_refund", "Записать возврат", idempotency=True),
    _write(
        "record_loan_received",
        "Записать получение кредита",
        idempotency=True,
    ),
    _write("create_transfer", "Перевод между счетами", idempotency=True),
    _write("update_transaction", "Исправить операцию"),
    _write("set_budget", "Задать план на месяц"),
    _write("move_budget", "Перенести план", idempotency=True),
    _write("set_goal", "Поставить цель"),
    _write(
        "preview_statement",
        "Разобрать выписку",
        method="mcp_preview_statement",
    ),
    _write(
        "import_statement",
        "Занести выписку",
        method="mcp_import_statement",
    ),
)

BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in CATALOG}


def bind(toolbox: McpToolBox, spec: ToolSpec) -> BetaAsyncFunctionTool[Any]:
    """Обёртка с проверкой аргументов по сигнатуре метода."""
    tool = beta_async_tool(getattr(toolbox, spec.method), name=spec.name)
    if not isinstance(tool, BetaAsyncFunctionTool):
        raise TypeError(f"{spec.method} — не асинхронный метод")
    return tool


def describe(toolbox: McpToolBox, spec: ToolSpec) -> types.Tool:
    """Описание инструмента для ``tools/list``.

    Схема — из сигнатуры, описание — из докстроки, как у бота.
    Подсказки (annotations) клиенты используют для подтверждения:
    ChatGPT без ``readOnlyHint`` считает инструмент пишущим и
    спрашивает разрешения. ``securitySchemes`` в ``_meta`` — для
    ChatGPT: по нему он понимает, какое право нужно инструменту.
    """
    tool = bind(toolbox, spec)
    schema = copy.deepcopy(compact_schema(tool.input_schema))
    if spec.idempotency:
        schema.setdefault("properties", {})[IDEMPOTENCY_ARG] = dict(
            _IDEMPOTENCY_SCHEMA
        )
    annotations = types.ToolAnnotations(
        title=spec.title,
        read_only_hint=spec.read_only,
        # Финансы — закрытый мир: только сайт, никаких внешних
        # сервисов.
        open_world_hint=False,
    )
    if not spec.read_only:
        # Удаления в каталоге нет, а запись и правка неразрушительны.
        # Повтор создаёт вторую операцию, поэтому не идемпотентны.
        annotations.destructive_hint = False
        annotations.idempotent_hint = False
    return types.Tool(
        name=spec.name,
        title=spec.title,
        description=spec.description or tool.description,
        input_schema=schema,
        annotations=annotations,
        _meta={
            "securitySchemes": [{"type": "oauth2", "scopes": [spec.scope]}]
        },
    )
