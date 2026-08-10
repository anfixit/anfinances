"""Клиент anfinances: логин, перелогин, разбор ответов, отказы."""

from typing import Any

import httpx
import pytest
import respx

from anfinances_bot.anfinances.client import (
    AnfinancesClient,
    AnfinancesError,
    AnfinancesUnavailableError,
)
from anfinances_bot.config import BotSettings

BASE = "http://backend:8000/api/v1"


def _settings(monkeypatch: Any) -> BotSettings:
    for key, value in {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "TELEGRAM_ALLOWED_USER_IDS": "111",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "OPENAI_API_KEY": "sk-test",
        "SINGLE_USER_EMAIL": "me@example.com",
        "SINGLE_USER_PASSWORD": "very-long-password-value",
        "BOT_DEFAULT_ACCOUNT_NAME": "Альфа",
    }.items():
        monkeypatch.setenv(key, value)
    return BotSettings()


def _login_ok(token: str = "tok-1") -> respx.Route:
    return respx.post(f"{BASE}/auth/login").mock(
        return_value=httpx.Response(
            200, json={"data": {"access_token": token}}
        )
    )


@respx.mock
async def test_logs_in_before_first_request(monkeypatch: Any) -> None:
    login = _login_ok()
    accounts = respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    client = AnfinancesClient(_settings(monkeypatch))
    await client.accounts()

    assert login.called
    assert accounts.calls[0].request.headers["authorization"] == "Bearer tok-1"
    await client.aclose()


@respx.mock
async def test_relogins_once_on_401(monkeypatch: Any) -> None:
    tokens = iter(["tok-old", "tok-new"])
    respx.post(f"{BASE}/auth/login").mock(
        side_effect=lambda request: httpx.Response(
            200, json={"data": {"access_token": next(tokens)}}
        )
    )
    responses = iter(
        [
            httpx.Response(401, json={"detail": "expired"}),
            httpx.Response(200, json={"data": []}),
        ]
    )
    route = respx.get(f"{BASE}/accounts").mock(
        side_effect=lambda request: next(responses)
    )

    client = AnfinancesClient(_settings(monkeypatch))
    await client.accounts()

    assert route.call_count == 2
    assert route.calls[1].request.headers["authorization"] == "Bearer tok-new"
    await client.aclose()


@respx.mock
async def test_second_401_is_not_retried_forever(
    monkeypatch: Any,
) -> None:
    """Один повтор, не бесконечный цикл."""
    _login_ok()
    route = respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(401, json={"detail": "nope"})
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesError):
        await client.accounts()
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_server_error_raises_unavailable(monkeypatch: Any) -> None:
    _login_ok()
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(503, text="down")
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesUnavailableError):
        await client.accounts()
    await client.aclose()


@respx.mock
async def test_network_error_raises_unavailable(monkeypatch: Any) -> None:
    respx.post(f"{BASE}/auth/login").mock(
        side_effect=httpx.ConnectError("нет сети")
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesUnavailableError):
        await client.accounts()
    await client.aclose()


@respx.mock
async def test_bad_credentials_report_clearly(monkeypatch: Any) -> None:
    respx.post(f"{BASE}/auth/login").mock(
        return_value=httpx.Response(401, json={"detail": "bad"})
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesError, match="SINGLE_USER"):
        await client.accounts()
    await client.aclose()


@respx.mock
async def test_validation_error_text_is_surfaced(
    monkeypatch: Any,
) -> None:
    _login_ok()
    respx.post(f"{BASE}/transactions").mock(
        return_value=httpx.Response(
            422, json={"detail": "Категория в архиве."}
        )
    )

    client = AnfinancesClient(_settings(monkeypatch))
    with pytest.raises(AnfinancesError, match="архиве"):
        await client.request("POST", "/transactions", json={})
    await client.aclose()


@respx.mock
async def test_parses_accounts(monkeypatch: Any) -> None:
    _login_ok()
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "a-1",
                        "name": "Альфа",
                        "currency_code": "RUB",
                        "current_balance": "1500.0000",
                    }
                ]
            },
        )
    )

    client = AnfinancesClient(_settings(monkeypatch))
    accounts = await client.accounts()
    assert accounts[0].name == "Альфа"
    assert accounts[0].currency_code == "RUB"
    await client.aclose()


@respx.mock
async def test_parses_profile_and_categories(monkeypatch: Any) -> None:
    _login_ok()
    respx.get(f"{BASE}/auth/me").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": "u-1",
                    "email": "me@example.com",
                    "timezone": "Asia/Tashkent",
                    "default_currency": "RUB",
                }
            },
        )
    )
    respx.get(f"{BASE}/categories").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "c-2",
                        "name": "Кофейни",
                        "kind": "expense",
                        "parent_id": "c-1",
                    }
                ]
            },
        )
    )

    client = AnfinancesClient(_settings(monkeypatch))
    profile = await client.me()
    assert profile.timezone == "Asia/Tashkent"

    categories = await client.categories()
    assert categories[0].parent_id == "c-1"
    await client.aclose()
