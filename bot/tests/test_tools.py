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
        ]

    async def accounts(self) -> list[AccountRead]:
        return self._accounts

    async def categories(self) -> list[CategoryRead]:
        return self._categories

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
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


async def test_readonly_tools_hit_expected_paths() -> None:
    box, client = _toolbox()
    await box.get_capital()
    await box.get_by_category(month="2026-08")
    await box.get_budget(month="2026-08")
    await box.list_transactions(limit=5)
    await box.get_credits()
    await box.get_credit_projection(credit_id="cr-1")
    await box.get_money_age()
    assert [(m, p) for m, p, _ in client.calls] == [
        ("GET", "/summary/dashboard"),
        ("GET", "/summary/by-category"),
        ("GET", "/budgets"),
        ("GET", "/transactions"),
        ("GET", "/credits"),
        ("GET", "/credits/cr-1/projection"),
        ("GET", "/summary/money-age"),
    ]


async def test_toolbox_exposes_all_tools() -> None:
    box, _ = _toolbox()
    names = {tool.name for tool in box.tools}
    assert names == {
        "create_expense",
        "create_income",
        "create_transfer",
        "create_credit_payment",
        "list_accounts",
        "list_categories",
        "get_capital",
        "get_by_category",
        "get_budget",
        "list_transactions",
        "get_credits",
        "get_credit_projection",
        "get_money_age",
    }
