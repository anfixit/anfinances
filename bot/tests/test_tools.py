"""Инструменты агента: запись и чтение через API anfinances."""

from decimal import Decimal
from typing import Any

import pytest

from anfinances_bot.agent.tools import ToolBox
from anfinances_bot.anfinances.schemas import AccountRead, CategoryRead

DEFAULTS = {"RUB": "Альфа", "UZS": "Наличные сумы"}


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.budgets: list[dict[str, Any]] = []
        self.transactions: list[dict[str, Any]] = []
        self.recurring: list[dict[str, Any]] = []
        self._accounts = [
            AccountRead(
                id="a-1",
                name="Альфа",
                currency_code="RUB",
                current_balance=Decimal("100"),
            ),
            AccountRead(
                id="a-2",
                name="Сбер",
                currency_code="RUB",
                current_balance=Decimal("200"),
            ),
            AccountRead(
                id="a-3",
                name="Наличные сумы",
                currency_code="UZS",
                current_balance=Decimal("500000"),
            ),
        ]
        self._categories = [
            CategoryRead(id="c-1", name="Еда", kind="expense"),
            CategoryRead(
                id="c-2", name="Кофейни", kind="expense", parent_id="c-1"
            ),
            CategoryRead(id="c-3", name="Зарплата", kind="income"),
            CategoryRead(id="c-4", name="Банк", kind="expense"),
            CategoryRead(
                id="c-5", name="Проценты", kind="expense", parent_id="c-4"
            ),
            CategoryRead(id="c-6", name="Софт", kind="expense"),
            CategoryRead(id="c-7", name="Развлечения", kind="expense"),
        ]

    async def accounts(self) -> list[AccountRead]:
        return self._accounts

    async def categories(self) -> list[CategoryRead]:
        return self._categories

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if method == "GET" and path == "/budgets":
            return list(self.budgets)
        if method == "GET" and path == "/recurring":
            return list(self.recurring)
        if method == "GET" and path == "/transactions":
            # Как настоящий API: отдаём страницами по limit.
            limit = int(kwargs.get("params", {}).get("limit", 20))
            cursor = kwargs.get("params", {}).get("cursor_id")
            start = 0
            if cursor is not None:
                ids = [row["id"] for row in self.transactions]
                start = ids.index(cursor) + 1
            return self.transactions[start : start + limit]
        if method == "POST" and path == "/categories":
            return {"id": "c-new", "name": "Новая", "kind": "expense"}
        if method == "POST" and path == "/transactions":
            return {"id": "tx-1"}
        if method == "POST" and path.endswith("/payments"):
            return {"id": "pay-1"}
        if method == "POST" and path == "/transfers":
            return {"id": "tr-1", "legs": []}
        if path == "/credits":
            return [{"id": "cr-1", "name": "Альфа Кредит"}]
        return []


def _toolbox(
    timezone: str = "Europe/Moscow",
    defaults: dict[str, str] | None = None,
) -> tuple[ToolBox, _FakeClient]:
    client = _FakeClient()
    box = ToolBox(
        client,
        default_accounts=DEFAULTS if defaults is None else defaults,
        timezone=timezone,
    )
    return box, client


async def test_expense_is_sent_with_positive_amount() -> None:
    """API принимает положительную сумму; знак ставит бэкенд."""
    box, client = _toolbox()
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/transactions")
    body = kwargs["json"]
    assert Decimal(body["amount"]) == Decimal("300")
    assert body["kind"] == "expense"
    assert body["account_id"] == "a-1"
    assert body["category_id"] == "c-2"


async def test_expense_records_created_id() -> None:
    box, _ = _toolbox()
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
    )
    assert box.last_created_id == "tx-1"


async def test_income_uses_income_category_tree() -> None:
    """«Еда» — расходная категория, для дохода её быть не должно."""
    box, client = _toolbox()
    result = await box.create_income(
        amount="100000",
        category_path="Еда",
        account_name="Альфа",
    )
    assert "не найдена" in result.casefold()
    assert client.calls == []

    await box.create_income(
        amount="100000",
        category_path="Зарплата",
        account_name="Альфа",
    )
    assert client.calls[0][2]["json"]["category_id"] == "c-3"


async def test_unknown_category_is_reported_not_guessed() -> None:
    box, client = _toolbox()
    result = await box.create_expense(
        amount="300",
        category_path="Такого нет",
        account_name="Альфа",
    )
    assert "не найдена" in result.casefold()
    assert client.calls == []


async def test_ambiguous_account_asks_instead_of_writing() -> None:
    """Два рублёвых счёта и счёт не назван — спрашиваем, а не гадаем."""
    box, client = _toolbox(defaults={"UZS": "Наличные сумы"})
    result = await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name=None,
        currency_code="RUB",
    )
    assert "уточнить" in result.casefold()
    assert client.calls == []
    assert [a.id for a in box.pending_accounts] == ["a-1", "a-2"]


async def test_default_account_is_picked_per_currency() -> None:
    box, client = _toolbox()
    await box.create_expense(
        amount="50000",
        category_path="Еда → Кофейни",
        currency_code="UZS",
    )
    assert client.calls[0][2]["json"]["account_id"] == "a-3"


async def test_naive_date_is_read_in_user_timezone() -> None:
    """21:00 в Ташкенте — это 16:00 UTC, а не 21:00 UTC."""
    box, client = _toolbox(timezone="Asia/Tashkent")
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
        when="2026-08-09T21:00",
    )
    assert client.calls[0][2]["json"]["date"] == "2026-08-09T16:00:00+00:00"


async def test_bare_date_becomes_noon_not_midnight() -> None:
    """Полночь легко перескакивает в соседние сутки при пересчёте."""
    box, client = _toolbox(timezone="Asia/Tashkent")
    await box.create_expense(
        amount="300",
        category_path="Еда → Кофейни",
        account_name="Альфа",
        when="2026-08-09",
    )
    assert client.calls[0][2]["json"]["date"] == "2026-08-09T07:00:00+00:00"


async def test_transfer_requires_both_amounts() -> None:
    """Решение Р-9: вторую сумму досчитывать нельзя."""
    box, client = _toolbox()
    with pytest.raises(ValueError):
        await box.create_transfer(
            from_account_name="Альфа",
            to_account_name="Наличные сумы",
            amount_from="20000",
            amount_to="",
        )
    assert client.calls == []


async def test_transfer_posts_both_amounts() -> None:
    box, client = _toolbox()
    await box.create_transfer(
        from_account_name="Альфа",
        to_account_name="Наличные сумы",
        amount_from="20000",
        amount_to="2800000",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/transfers")
    assert kwargs["json"]["amount_from"] == "20000"
    assert kwargs["json"]["amount_to"] == "2800000"


async def test_credit_payment_splits_principal_and_interest() -> None:
    box, client = _toolbox()
    await box.create_credit_payment(
        credit_id="cr-1",
        total_amount="13395.51",
        principal_amount="5415.70",
        interest_amount="7979.81",
        account_name="Альфа",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/credits/cr-1/payments")
    body = kwargs["json"]
    assert body["payment_account_id"] == "a-1"
    assert body["total_amount"] == "13395.51"
    assert body["principal_amount"] == "5415.70"
    assert body["interest_amount"] == "7979.81"


async def test_credit_payment_parts_must_add_up() -> None:
    """Бэкенд это тоже проверит, но ошибку лучше поймать здесь."""
    box, client = _toolbox()
    result = await box.create_credit_payment(
        credit_id="cr-1",
        total_amount="10000",
        principal_amount="5000",
        interest_amount="4000",
        account_name="Альфа",
    )
    assert "не сходится" in result.casefold()
    assert client.calls == []


async def test_credit_payment_attaches_interest_category() -> None:
    box, client = _toolbox()
    await box.create_credit_payment(
        credit_id="cr-1",
        total_amount="1000",
        principal_amount="0",
        interest_amount="1000",
        account_name="Альфа",
        interest_category_path="Банк → Проценты",
    )
    assert client.calls[0][2]["json"]["interest_category_id"] == "c-5"


async def test_update_sends_only_given_fields() -> None:
    box, client = _toolbox()
    await box.update_transaction(
        transaction_id="tx-1", category_path="Еда → Кофейни"
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("PATCH", "/transactions/tx-1")
    assert kwargs["json"] == {"category_id": "c-2"}


async def test_update_without_fields_changes_nothing() -> None:
    box, client = _toolbox()
    result = await box.update_transaction(transaction_id="tx-1")
    assert "нечего менять" in result.casefold()
    assert client.calls == []


async def test_delete_transaction_hits_endpoint() -> None:
    box, client = _toolbox()
    await box.delete_transaction(transaction_id="tx-1")
    assert client.calls[0][:2] == ("DELETE", "/transactions/tx-1")


async def test_readonly_tools_hit_expected_paths() -> None:
    box, client = _toolbox()
    await box.get_capital()
    await box.get_by_category(month="2026-08")
    await box.get_budget(month="2026-08")
    await box.list_transactions(limit=5)
    await box.get_credits()
    await box.get_credit_projection(credit_id="cr-1")
    await box.get_money_age()
    await box.get_daily_allowance()
    await box.list_recurring()
    assert [(m, p) for m, p, _ in client.calls] == [
        ("GET", "/summary/dashboard"),
        ("GET", "/summary/by-category"),
        ("GET", "/budgets"),
        ("GET", "/transactions"),
        ("GET", "/credits"),
        ("GET", "/credits/cr-1/projection"),
        ("GET", "/summary/money-age"),
        ("GET", "/summary/daily-allowance"),
        ("GET", "/recurring"),
    ]


async def test_set_budget_creates_when_absent() -> None:
    box, client = _toolbox()
    await box.set_budget(
        month="2026-09", category_path="Еда → Кофейни", planned="19500"
    )
    assert client.calls[0][:2] == ("GET", "/budgets")
    method, path, kwargs = client.calls[1]
    assert (method, path) == ("POST", "/budgets")
    assert kwargs["json"] == {
        "month": "2026-09",
        "category_id": "c-2",
        "planned": "19500",
        "rollover": False,
    }


async def test_set_budget_updates_when_already_there() -> None:
    """Повторная просьба не должна падать «уже есть»."""
    box, client = _toolbox()
    client.budgets = [{"id": "b-1", "category_id": "c-2", "planned": "100"}]
    await box.set_budget(
        month="2026-09", category_path="Еда → Кофейни", planned="19500"
    )
    method, path, kwargs = client.calls[1]
    assert (method, path) == ("PATCH", "/budgets/b-1")
    assert kwargs["json"]["planned"] == "19500"


async def test_set_budget_refuses_unknown_category() -> None:
    box, client = _toolbox()
    result = await box.set_budget(
        month="2026-09", category_path="Такого нет", planned="1"
    )
    assert "не найдена" in result.casefold()
    assert client.calls == []


async def test_create_category_resolves_parent_by_name() -> None:
    box, client = _toolbox()
    await box.create_category(name="Подписки", kind="expense", parent="Софт")
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/categories")
    assert kwargs["json"]["name"] == "Подписки"
    assert kwargs["json"]["parent_id"] == "c-6"


async def test_create_category_rejects_unknown_parent() -> None:
    box, client = _toolbox()
    result = await box.create_category(
        name="Подписки", kind="expense", parent="Нету"
    )
    assert "не найдена" in result.casefold()
    assert client.calls == []


async def test_create_account_posts_type_and_currency() -> None:
    box, client = _toolbox()
    await box.create_account(
        name="Новый", account_type="card", currency_code="rub"
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/accounts")
    assert kwargs["json"]["type"] == "card"
    assert kwargs["json"]["currency_code"] == "RUB"


async def test_create_account_rejects_unknown_type() -> None:
    box, client = _toolbox()
    result = await box.create_account(
        name="Новый", account_type="кошелёк", currency_code="RUB"
    )
    assert "тип счёта" in result.casefold()
    assert client.calls == []


async def test_add_recurring_uses_category_path() -> None:
    box, client = _toolbox()
    await box.add_recurring(
        name="Аренда", category_path="Еда → Кофейни", monthly_amount="19500"
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/recurring")
    assert kwargs["json"]["category_id"] == "c-2"
    assert kwargs["json"]["monthly_amount"] == "19500"
    assert kwargs["json"]["required"] == "required"


async def test_create_credit_posts_terms() -> None:
    box, client = _toolbox()
    await box.create_credit(
        name="Альфа Кредит",
        principal_initial="685840",
        currency_code="RUB",
        annual_rate="21.59",
        term_months=60,
        monthly_payment="10700",
        payment_day=4,
        account_name="Альфа",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/credits")
    assert kwargs["json"]["principal_initial"] == "685840"
    assert kwargs["json"]["linked_account_id"] == "a-1"


async def test_toolbox_exposes_all_tools() -> None:
    box, _ = _toolbox()
    names = {tool.name for tool in box.tools}
    assert names == {
        "create_expense",
        "create_income",
        "create_transfer",
        "create_credit_payment",
        "import_statement",
        "update_transaction",
        "delete_transaction",
        "delete_credit_payment",
        "archive_account",
        "set_budget",
        "move_budget",
        "create_category",
        "create_account",
        "create_credit",
        "add_recurring",
        "update_recurring",
        "delete_recurring",
        "list_accounts",
        "list_categories",
        "list_recurring",
        "get_capital",
        "get_by_category",
        "get_budget",
        "get_daily_allowance",
        "list_transactions",
        "get_credits",
        "get_credit_projection",
        "get_money_age",
        "list_credit_payments",
    }


def _row(**over: Any) -> dict[str, Any]:
    base = {
        "date": "2026-08-01",
        "amount": "300",
        "kind": "expense",
        "category_path": "Еда → Кофейни",
    }
    base.update(over)
    return base


async def test_statement_import_posts_all_rows_at_once() -> None:
    """Двести операций двумястами вызовами — долго и дорого."""
    box, client = _toolbox()
    result = await box.import_statement(
        account_name="Альфа",
        rows=[_row(), _row(amount="450", comment="такси")],
    )
    posts = [c for c in client.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == "/import/transactions"
    items = posts[0][2]["json"]["items"]
    assert len(items) == 2
    assert items[0]["account_id"] == "a-1"
    assert items[0]["category_id"] == "c-2"
    assert items[1]["comment"] == "такси"
    assert "2" in result


async def test_statement_import_skips_existing_rows() -> None:
    """Повторная выгрузка за тот же период не должна задваивать."""
    box, client = _toolbox()
    client.transactions = [
        {
            "account_id": "a-1",
            "amount": "300.0000",
            "date": "2026-08-01T09:00:00+00:00",
            "kind": "expense",
        }
    ]
    result = await box.import_statement(
        account_name="Альфа",
        rows=[_row(), _row(amount="450")],
    )
    post = next(c for c in client.calls if c[0] == "POST")
    items = post[2]["json"]["items"]
    assert len(items) == 1
    assert items[0]["amount"] == "450"
    assert "1" in result


async def test_statement_import_reports_unknown_categories() -> None:
    """Молча пропустить строку — потерять операцию незаметно."""
    box, client = _toolbox()
    result = await box.import_statement(
        account_name="Альфа",
        rows=[_row(), _row(category_path="Ерунда")],
    )
    assert "ерунда" in result.casefold()
    assert not [c for c in client.calls if c[0] == "POST"]


async def test_statement_import_needs_a_known_account() -> None:
    box, client = _toolbox()
    result = await box.import_statement(account_name="Нету", rows=[_row()])
    assert "счёт не найден" in result.casefold()
    assert client.calls == []


async def test_statement_import_rejects_empty_input() -> None:
    box, client = _toolbox()
    result = await box.import_statement(account_name="Альфа", rows=[])
    assert "пуст" in result.casefold()
    assert client.calls == []


async def test_statement_import_duplicate_inside_one_file_is_kept() -> None:
    """Две одинаковые покупки за день — обычное дело, не дубль."""
    box, client = _toolbox()
    await box.import_statement(account_name="Альфа", rows=[_row(), _row()])
    post = next(c for c in client.calls if c[0] == "POST")
    items = post[2]["json"]["items"]
    assert len(items) == 2


async def test_statement_import_pages_through_existing_rows() -> None:
    """Сверка обязана дочитать все страницы, а не первую сотню."""
    box, client = _toolbox()
    # Ровно страница «чужих» операций, а следом та, что уже записана.
    client.transactions = [
        {
            "id": f"old-{i}",
            "account_id": "a-1",
            "amount": f"{i + 1}.0000",
            "date": "2026-08-01T09:00:00+00:00",
        }
        for i in range(100)
    ] + [
        {
            "id": "old-dup",
            "account_id": "a-1",
            "amount": "300.0000",
            "date": "2026-08-01T09:00:00+00:00",
        }
    ]

    result = await box.import_statement(account_name="Альфа", rows=[_row()])
    assert not [c for c in client.calls if c[0] == "POST"]
    assert "уже были записаны" in result.casefold()


async def test_move_budget_sends_both_categories() -> None:
    box, client = _toolbox()
    result = await box.move_budget(
        month="2026-08",
        from_category_path="Развлечения",
        to_category_path="Еда → Кофейни",
        amount="1500",
    )
    method, path, kwargs = client.calls[0]
    assert (method, path) == ("POST", "/budgets/move")
    assert kwargs["json"]["from_category_id"] == "c-7"
    assert kwargs["json"]["to_category_id"] == "c-2"
    assert kwargs["json"]["amount"] == "1500"
    assert "1500" in result


async def test_move_budget_rejects_unknown_category() -> None:
    box, client = _toolbox()
    result = await box.move_budget(
        month="2026-08",
        from_category_path="Ерунда",
        to_category_path="Еда → Кофейни",
        amount="100",
    )
    assert "не найдена" in result.casefold()
    assert client.calls == []


async def test_update_can_move_operation_to_another_account() -> None:
    box, client = _toolbox()
    await box.update_transaction(transaction_id="tx-1", account_name="Сбер")
    method, path, kwargs = client.calls[-1]
    assert (method, path) == ("PATCH", "/transactions/tx-1")
    assert kwargs["json"] == {"account_id": "a-2"}


async def test_update_rejects_unknown_account() -> None:
    box, client = _toolbox()
    result = await box.update_transaction(
        transaction_id="tx-1", account_name="Нету такого"
    )
    assert "счёт не найден" in result.casefold()
    assert not [c for c in client.calls if c[0] == "PATCH"]


async def test_credit_payment_can_be_deleted() -> None:
    box, client = _toolbox()
    result = await box.delete_credit_payment(
        credit_id="cr-1", payment_id="pay-9"
    )
    assert client.calls[0][:2] == (
        "DELETE",
        "/credits/cr-1/payments/pay-9",
    )
    assert "долг" in result.casefold()


async def test_account_with_balance_needs_force() -> None:
    """Без подтверждения бэкенд откажет — и это правильно."""
    box, client = _toolbox()
    await box.archive_account(account_name="Сбер")
    assert client.calls[-1][2]["params"] == {}

    await box.archive_account(account_name="Сбер", force=True)
    assert client.calls[-1][2]["params"] == {"force": "true"}


async def test_archiving_unknown_account_is_reported() -> None:
    box, client = _toolbox()
    result = await box.archive_account(account_name="Нету")
    assert "не найден" in result.casefold()
    assert client.calls == []


def _plan(*names: str) -> list[dict[str, Any]]:
    return [
        {"id": f"r-{i}", "name": name, "is_archived": False}
        for i, name in enumerate(names)
    ]


async def test_recurring_row_is_edited_not_duplicated() -> None:
    """Две строки на одну трату завышают резерв."""
    box, client = _toolbox()
    client.recurring = _plan("Стационарный интернет (Тольятти)")

    result = await box.update_recurring(name="Тольятти", monthly_amount="750")
    method, path, kwargs = client.calls[-1]
    assert (method, path) == ("PATCH", "/recurring/r-0")
    assert kwargs["json"] == {"monthly_amount": "750"}
    assert "обновлена" in result


async def test_recurring_row_is_deleted() -> None:
    box, client = _toolbox()
    client.recurring = _plan("Интернет", "Мобильная связь")

    result = await box.delete_recurring(name="Мобильная связь")
    assert client.calls[-1][:2] == ("DELETE", "/recurring/r-1")
    assert "убрана" in result


async def test_ambiguous_name_asks_instead_of_guessing() -> None:
    """Точного совпадения нет, а частичных два — выбирать нельзя."""
    box, client = _toolbox()
    client.recurring = _plan("Йота модем", "Йота телефон")

    result = await box.delete_recurring(name="Йота")
    assert "несколько строк" in result
    assert not [c for c in client.calls if c[0] == "DELETE"]


async def test_exact_name_wins_over_partial() -> None:
    """Точное «Интернет» не должно спотыкаться о «Стационарный»."""
    box, client = _toolbox()
    client.recurring = _plan("Интернет", "Стационарный интернет")

    await box.delete_recurring(name="Интернет")
    assert client.calls[-1][:2] == ("DELETE", "/recurring/r-0")


async def test_unknown_row_lists_what_exists() -> None:
    box, client = _toolbox()
    client.recurring = _plan("Аренда")
    result = await box.update_recurring(name="Ипотека", monthly_amount="1")
    assert "не найдена" in result
    assert "Аренда" in result
