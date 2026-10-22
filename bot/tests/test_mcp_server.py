"""MCP-сервер: вход по токену, права, инструменты, повторы, выписка.

Сайт подменён ``httpx.MockTransport``: он знает два токена — на
чтение и на запись — и записывает каждый запрос, чтобы проверить,
что в сайт ушёл ровно токен вызывающего.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from anfinances_bot.mcp_server.auth import TokenGate
from anfinances_bot.mcp_server.catalog import CATALOG
from anfinances_bot.mcp_server.config import McpSettings
from anfinances_bot.mcp_server.server import build_app

BACKEND = "http://backend:8000/api/v1"
READ = "anf_oat_read-token"
WRITE = "anf_oat_write-token"
METADATA_URL = "https://anfinances.ru/.well-known/oauth-protected-resource/mcp"

IDENTITIES: dict[str, dict[str, Any]] = {
    READ: {
        "connection_id": "conn-read",
        "user_id": "u-1",
        "scopes": ["finance.read"],
        "kind": "oauth",
        "name": "ChatGPT",
    },
    # Запись включает чтение: отдельного finance.read у токена нет.
    WRITE: {
        "connection_id": "conn-write",
        "user_id": "u-1",
        "scopes": ["finance.write"],
        "kind": "oauth",
        "name": "Claude",
    },
}

CATEGORIES = [
    {"id": "c-1", "name": "Еда", "kind": "expense", "parent_id": None},
    {"id": "c-2", "name": "Кофейни", "kind": "expense", "parent_id": "c-1"},
]
ACCOUNTS = [
    {
        "id": "a-1",
        "name": "Альфа",
        "currency_code": "RUB",
        "current_balance": "1000",
    }
]


class FakeBackend:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.whoami = 0
        self.created = 0
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return httpx.Response(502)
        path = request.url.path.removeprefix("/api/v1")
        token = request.headers.get("authorization", "")
        identity = IDENTITIES.get(token.removeprefix("Bearer "))
        if not token.startswith("Bearer ") or identity is None:
            return httpx.Response(401, json={"detail": "bad token"})
        if path == "/ai/whoami":
            self.whoami += 1
            return _ok(identity)
        # Сайт сам режет запись по правам — как будет на проде.
        if (
            request.method != "GET"
            and "finance.write" not in identity["scopes"]
        ):
            return httpx.Response(403, json={"detail": "read-only token"})
        return self._route(request.method, path, request)

    def _route(
        self, method: str, path: str, request: httpx.Request
    ) -> httpx.Response:
        if path == "/auth/me":
            return _ok(
                {
                    "id": "u-1",
                    "email": "me@example.com",
                    "timezone": "Asia/Tashkent",
                    "default_currency": "RUB",
                }
            )
        if path == "/accounts":
            return _ok(ACCOUNTS)
        if path == "/categories":
            return _ok(CATEGORIES)
        if path == "/payees":
            return _ok([])
        if path == "/transactions" and method == "GET":
            return _ok([])
        if path == "/transactions" and method == "POST":
            self.created += 1
            return _ok({"id": f"t-{self.created}"})
        if path == "/import/transactions":
            return _ok({"created": 1})
        if path == "/summary/dashboard":
            return _ok(
                {
                    "accounts": [
                        {
                            "account_id": "a-1",
                            "name": "Альфа",
                            "currency_code": "RUB",
                            "balance": "1000",
                            "balance_rub": "1000",
                        }
                    ],
                    "total_capital_rub": "1000",
                    "total_credit_debt_rub": "0",
                    "is_total_complete": True,
                    "missing_rate_currencies": [],
                }
            )
        if path == "/summary/daily-allowance":
            return _ok(
                {
                    "until": "2026-10-31",
                    "days_left": 10,
                    "liquid_rub": "1000",
                    "obligations_rub": "0",
                    "safe_to_spend_rub": "1000",
                    "per_day_rub": "100",
                    "unallocated_rub": "0",
                    "is_short": False,
                    "is_overplanned": False,
                }
            )
        if path == "/summary/money-age":
            return _ok(
                {
                    "previous_month": "2026-09",
                    "current_month": "2026-10",
                    "previous_month_income_rub": "5000",
                    "current_month_expense_rub": "4000",
                    "coverage": "1.25",
                    "is_covered": True,
                    "age_days": 34,
                }
            )
        if path in (
            "/summary/income-by-category",
            "/summary/upcoming-payments",
            "/credits/payoff-plan",
        ):
            return _ok({"path": path, "query": dict(request.url.params)})
        return httpx.Response(404, json={"detail": f"no route {path}"})

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]


def _ok(data: Any) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
async def mcp(backend: FakeBackend) -> AsyncIterator[httpx.AsyncClient]:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(backend), base_url=BACKEND
    )
    app = build_app(McpSettings(anfinances_base_url=BACKEND), http)
    # Lifespan входит и выходит в одной задаче — как у uvicorn. Фикстура
    # pytest-asyncio делает подготовку и уборку в разных задачах, и
    # группа задач менеджера сессий на это ругается.
    started, stop = asyncio.Event(), asyncio.Event()

    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            started.set()
            await stop.wait()

    lifespan = asyncio.create_task(run_lifespan())
    await started.wait()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8100",
    ) as client:
        yield client
    stop.set()
    await lifespan
    await http.aclose()


async def _rpc(
    client: httpx.AsyncClient,
    token: str | None,
    method: str,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        },
        headers=headers,
    )


async def _tools(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    response = await _rpc(client, token, "tools/list")
    assert response.status_code == 200, response.text
    return {t["name"]: t for t in response.json()["result"]["tools"]}


async def _call(
    client: httpx.AsyncClient, token: str, name: str, **arguments: Any
) -> dict[str, Any]:
    response = await _rpc(
        client, token, "tools/call", {"name": name, "arguments": arguments}
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()["result"]
    return result


def _text(result: dict[str, Any]) -> str:
    return "\n".join(block["text"] for block in result["content"])


# --- вход -----------------------------------------------------------


async def test_no_token_gets_401_with_resource_metadata(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    response = await _rpc(mcp, None, "tools/list")

    assert response.status_code == 401
    # Просим оба права: иначе ChatGPT запросит только чтение, и
    # человеку на экране согласия нечего будет включить.
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{METADATA_URL}", '
        'scope="finance.read finance.write"'
    )
    # Без токена в сайт не ходим вовсе.
    assert backend.requests == []


async def test_unknown_token_gets_invalid_token(
    mcp: httpx.AsyncClient,
) -> None:
    response = await _rpc(mcp, "anf_oat_forged", "tools/list")

    assert response.status_code == 401
    header = response.headers["www-authenticate"]
    assert header.startswith('Bearer error="invalid_token"')
    assert f'resource_metadata="{METADATA_URL}"' in header
    assert 'scope="finance.read finance.write"' in header


async def test_backend_outage_is_503_not_401(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    """Сбой сайта не должен выглядеть как плохой токен."""
    backend.down = True

    response = await _rpc(mcp, READ, "tools/list")

    assert response.status_code == 503
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize(
    "path",
    [
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-protected-resource",
    ],
)
async def test_protected_resource_metadata(
    mcp: httpx.AsyncClient, path: str
) -> None:
    response = await mcp.get(path)

    assert response.status_code == 200
    assert response.json() == {
        "resource": "https://anfinances.ru/mcp",
        "authorization_servers": ["https://anfinances.ru"],
        "scopes_supported": ["finance.read", "finance.write"],
        "bearer_methods_supported": ["header"],
        "resource_name": "anfinances",
    }


async def test_whoami_is_cached_between_requests(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    await _tools(mcp, READ)
    await _tools(mcp, READ)
    await _call(mcp, READ, "list_accounts")

    assert backend.whoami == 1


async def test_gate_asks_again_after_ttl(backend: FakeBackend) -> None:
    now = [0.0]
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(backend), base_url=BACKEND
    )
    gate = TokenGate(http, clock=lambda: now[0])

    first = await gate.identify(READ)
    await gate.identify(READ)
    now[0] = 31.0
    await gate.identify(READ)

    assert first is not None and first.connection_id == "conn-read"
    assert backend.whoami == 2
    await http.aclose()


async def test_gate_rejects_token_for_another_resource() -> None:
    def whoami(request: httpx.Request) -> httpx.Response:
        return _ok({**IDENTITIES[READ], "resource": "https://evil.example"})

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(whoami), base_url=BACKEND
    )
    gate = TokenGate(http, expected_resource="https://anfinances.ru/mcp")

    assert await gate.identify(READ) is None
    await http.aclose()


async def test_caller_token_is_forwarded_verbatim(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    result = await _call(mcp, READ, "list_accounts")

    assert not result["isError"]
    assert "Альфа: 1000 RUB" in _text(result)
    assert backend.requests
    assert {r.headers["authorization"] for r in backend.requests} == {
        f"Bearer {READ}"
    }
    # Никакого входа логином и паролем.
    assert all(r.url.path != "/api/v1/auth/login" for r in backend.requests)


# --- права ----------------------------------------------------------


async def test_read_token_sees_no_write_tools(mcp: httpx.AsyncClient) -> None:
    tools = await _tools(mcp, READ)

    assert "list_accounts" in tools
    assert "get_financial_overview" in tools
    for name in ("create_expense", "import_statement", "set_budget"):
        assert name not in tools
    # Сверка ходит POST-ом, сайт пустит её только с правом записи.
    assert "check_account_balance" not in tools


async def test_read_token_cannot_call_write_tool(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    result = await _call(
        mcp, READ, "create_expense", amount="300", category_path="Еда"
    )

    assert result["isError"] is True
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    assert 'error="insufficient_scope"' in challenge
    assert 'scope="finance.write"' in challenge
    # До сайта вызов не дошёл.
    assert backend.writes() == []


async def test_write_token_sees_and_calls_write_tools(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    tools = await _tools(mcp, WRITE)
    assert "create_expense" in tools
    assert "list_accounts" in tools

    result = await _call(
        mcp,
        WRITE,
        "create_expense",
        amount="300",
        category_path="Еда → Кофейни",
        payee="Кофе Хауз",
    )

    assert not result["isError"], _text(result)
    assert "Записано: Еда → Кофейни — 300, Альфа" in _text(result)
    (post,) = backend.writes()
    assert post.url.path == "/api/v1/transactions"
    assert post.headers["authorization"] == f"Bearer {WRITE}"


def test_catalog_has_no_delete_or_archive() -> None:
    names = {spec.name for spec in CATALOG}

    assert not any(
        name.startswith(("delete_", "archive_", "restore_")) for name in names
    )
    assert len(names) == len(CATALOG)


async def test_annotations(mcp: httpx.AsyncClient) -> None:
    tools = await _tools(mcp, WRITE)

    read = tools["list_accounts"]["annotations"]
    assert read["readOnlyHint"] is True
    write = tools["create_expense"]["annotations"]
    assert write["readOnlyHint"] is False
    assert write["destructiveHint"] is False
    assert write["idempotentHint"] is False
    assert (
        "idempotency_key"
        in (tools["create_expense"]["inputSchema"]["properties"])
    )
    assert (
        "idempotency_key"
        not in (tools["update_transaction"]["inputSchema"]["properties"])
    )
    assert tools["create_expense"]["_meta"]["securitySchemes"] == [
        {"type": "oauth2", "scopes": ["finance.write"]}
    ]
    # У каждого инструмента есть первая фраза — её показывает ChatGPT.
    for tool in tools.values():
        assert tool["description"].split("\n")[0].strip()


async def test_unknown_tool_is_protocol_error(mcp: httpx.AsyncClient) -> None:
    response = await _rpc(
        mcp,
        WRITE,
        "tools/call",
        {"name": "delete_transaction", "arguments": {"transaction_id": "t"}},
    )

    assert "error" in response.json()


async def test_bad_arguments_explain_themselves(
    mcp: httpx.AsyncClient,
) -> None:
    result = await _call(mcp, WRITE, "create_expense", amount="300")

    assert result["isError"] is True
    assert "category_path" in _text(result)


# --- повторы --------------------------------------------------------


async def test_idempotency_key_dedupes_writes(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    args = {"amount": "300", "category_path": "Еда → Кофейни"}

    first = await _call(
        mcp, WRITE, "create_expense", idempotency_key="k-1", **args
    )
    again = await _call(
        mcp, WRITE, "create_expense", idempotency_key="k-1", **args
    )

    assert backend.created == 1
    assert _text(again) == _text(first)


async def test_same_key_other_arguments_is_refused(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    await _call(
        mcp,
        WRITE,
        "create_expense",
        idempotency_key="k-1",
        amount="300",
        category_path="Еда → Кофейни",
    )
    clash = await _call(
        mcp,
        WRITE,
        "create_expense",
        idempotency_key="k-1",
        amount="500",
        category_path="Еда → Кофейни",
    )

    assert clash["isError"] is True
    assert backend.created == 1


async def test_without_key_each_call_writes(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    args = {"amount": "300", "category_path": "Еда → Кофейни"}

    await _call(mcp, WRITE, "create_expense", **args)
    await _call(mcp, WRITE, "create_expense", **args)

    assert backend.created == 2


# --- выписка --------------------------------------------------------

ROWS = [
    {
        "date": "2026-10-01",
        "amount": "300",
        "kind": "expense",
        "category_path": "Еда → Кофейни",
        "payee": "Кофе Хауз",
    }
]


def _preview_id(text: str) -> str:
    line = next(x for x in text.splitlines() if x.startswith("preview_id:"))
    return line.split(":", 1)[1].strip()


async def test_import_requires_preview_id(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    preview = await _call(
        mcp, WRITE, "preview_statement", account_name="Альфа", rows=ROWS
    )
    assert not preview["isError"], _text(preview)
    preview_id = _preview_id(_text(preview))
    assert backend.writes() == []

    wrong = await _call(mcp, WRITE, "import_statement", preview_id="nope")
    assert "нет" in _text(wrong)
    assert backend.writes() == []

    done = await _call(mcp, WRITE, "import_statement", preview_id=preview_id)
    assert "Занесено операций: «Альфа» — 1" in _text(done)
    imports = [
        r
        for r in backend.writes()
        if r.url.path.endswith("/import/transactions")
    ]
    assert len(imports) == 1

    # Повтор того же id ничего не задваивает.
    await _call(mcp, WRITE, "import_statement", preview_id=preview_id)
    assert len(backend.writes()) == 1


async def test_import_tool_demands_preview_id_argument(
    mcp: httpx.AsyncClient,
) -> None:
    tools = await _tools(mcp, WRITE)

    schema = tools["import_statement"]["inputSchema"]
    assert schema["required"] == ["preview_id"]


# --- новые чтения ---------------------------------------------------


async def test_financial_overview_combines_three_summaries(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    result = await _call(mcp, READ, "get_financial_overview")

    text = _text(result)
    assert "Капитал: 1000 ₽" in text
    assert "Можно тратить в день: 100 ₽" in text
    assert "Возраст денег: 34 дн." in text
    paths = {r.url.path for r in backend.requests}
    assert {
        "/api/v1/summary/dashboard",
        "/api/v1/summary/daily-allowance",
        "/api/v1/summary/money-age",
    } <= paths


async def test_analytics_tools_hit_contract_endpoints(
    mcp: httpx.AsyncClient, backend: FakeBackend
) -> None:
    await _call(mcp, READ, "get_income_by_category", month="2026-09")
    await _call(mcp, READ, "get_upcoming_payments", days=14)
    plan = await _call(
        mcp,
        READ,
        "get_payoff_plan",
        strategy="snowball",
        extra_monthly="5000,50",
    )

    assert not plan["isError"], _text(plan)
    seen = {
        (r.url.path, tuple(sorted(r.url.params.items())))
        for r in backend.requests
    }
    assert (
        "/api/v1/summary/income-by-category",
        (("month", "2026-09"),),
    ) in seen
    assert ("/api/v1/summary/upcoming-payments", (("days", "14"),)) in seen
    assert (
        "/api/v1/credits/payoff-plan",
        (("extra_monthly", "5000.50"), ("strategy", "snowball")),
    ) in seen


def test_settings_start_without_bot_secrets(monkeypatch: Any) -> None:
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "SINGLE_USER_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = McpSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.mcp_public_url == "https://anfinances.ru/mcp"
    assert settings.resource_metadata_url == METADATA_URL
    assert settings.bot_default_accounts == {}
