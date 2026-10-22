"""Личные токены, /ai/whoami, отзыв, лимит, аудит."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domains.ai.models import AiConnection, AiToken
from app.domains.ai.policy import deny_reason
from app.domains.ai.scopes import (
    InvalidScopeError,
    normalize_scopes,
    parse_scopes,
)
from app.domains.ai.tokens import hash_secret, pkce_matches
from tests.ai_support import API, RESOURCE, ai_env, make_settings, pkce_pair


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_personal_token_shown_once_and_stored_as_hash() -> None:
    async with ai_env() as env:
        r = await env.client.post(
            f"{API}/ai/connections",
            json={"name": "  Claude дома  ", "scopes": ["finance.write"]},
            headers=env.site,
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        token = data["token"]
        assert token.startswith("anf_pat_")
        assert len(token) == len("anf_pat_") + 43
        assert data["connection"]["name"] == "Claude дома"
        assert data["connection"]["scopes"] == [
            "finance.read",
            "finance.write",
        ]

        async with env.sessionmaker() as s:
            rows = (await s.execute(select(AiToken))).scalars().all()
        assert [row.token_hash for row in rows] == [hash_secret(token)]

        # В списке токена нет — показать его заново нельзя.
        r = await env.client.get(f"{API}/ai/connections", headers=env.site)
        assert r.status_code == 200
        listed = r.json()["data"]
        assert len(listed) == 1
        assert "token" not in listed[0]
        assert token not in r.text
        assert listed[0]["kind"] == "personal"


async def test_whoami_for_personal_token() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.read"])
        r = await env.client.get(f"{API}/ai/whoami", headers=_bearer(token))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["user_id"] == str(env.user_id)
        assert data["kind"] == "personal"
        assert data["scopes"] == ["finance.read"]
        assert data["name"] == "Тест"
        assert data["resource"] == RESOURCE
        assert data["expires_at"] is None
        assert data["timezone"] == "Europe/Moscow"
        assert data["default_currency"] == "RUB"

        # Профиль читать можно — MCP-сервер берёт оттуда пояс и валюту.
        r = await env.client.get(f"{API}/auth/me", headers=_bearer(token))
        assert r.status_code == 200
        r = await env.client.post(f"{API}/auth/logout", headers=_bearer(token))
        assert r.status_code == 403


async def test_whoami_rejects_site_jwt_and_garbage() -> None:
    async with ai_env() as env:
        r = await env.client.get(f"{API}/ai/whoami", headers=env.site)
        assert r.status_code == 401
        for bad in ("anf_pat_nope", "anf_oat_nope", "anf_ort_x", "x.y.z"):
            r = await env.client.get(f"{API}/ai/whoami", headers=_bearer(bad))
            assert r.status_code == 401, bad
        r = await env.client.get(f"{API}/ai/whoami")
        assert r.status_code == 401


async def test_revoked_token_is_rejected() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.write"])
        r = await env.client.get(f"{API}/ai/connections", headers=env.site)
        conn_id = r.json()["data"][0]["id"]

        r = await env.client.post(
            f"{API}/ai/connections/{conn_id}/revoke", headers=env.site
        )
        assert r.status_code == 200
        r = await env.client.get(f"{API}/ai/whoami", headers=_bearer(token))
        assert r.status_code == 401
        r = await env.client.get(f"{API}/accounts", headers=_bearer(token))
        assert r.status_code == 401
        r = await env.client.get(f"{API}/ai/connections", headers=env.site)
        assert r.json()["data"] == []


async def test_cannot_revoke_someone_elses_connection() -> None:
    async with ai_env() as env:
        r = await env.client.post(
            f"{API}/ai/connections/00000000-0000-0000-0000-000000000001"
            "/revoke",
            headers=env.site,
        )
        assert r.status_code == 404


async def test_personal_token_validation() -> None:
    async with ai_env() as env:
        for body in (
            {"name": "", "scopes": ["finance.read"]},
            {"name": "x", "scopes": []},
            {"name": "x", "scopes": ["admin"]},
            {"name": "x" * 101, "scopes": ["finance.read"]},
        ):
            r = await env.client.post(
                f"{API}/ai/connections", json=body, headers=env.site
            )
            assert r.status_code == 422, body


async def test_last_used_updates_at_most_once_a_minute() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.read"])
        await env.client.get(f"{API}/accounts", headers=_bearer(token))
        async with env.sessionmaker() as s:
            conn = (await s.execute(select(AiConnection))).scalar_one()
            first = conn.last_used_at
            assert first is not None
            # Минуту назад — следующий запрос обязан обновить.
            conn.last_used_at = datetime.now(UTC) - timedelta(minutes=2)
            await s.commit()

        await env.client.get(f"{API}/accounts", headers=_bearer(token))
        async with env.sessionmaker() as s:
            conn = (await s.execute(select(AiConnection))).scalar_one()
            second = conn.last_used_at
            assert second is not None
        await env.client.get(f"{API}/accounts", headers=_bearer(token))
        async with env.sessionmaker() as s:
            conn = (await s.execute(select(AiConnection))).scalar_one()
            assert conn.last_used_at == second


async def test_rate_limit_per_connection() -> None:
    async with ai_env(make_settings(ai_rate_limit_per_minute=3)) as env:
        token = await env.personal_token(["finance.read"])
        other = await env.personal_token(["finance.read"])
        codes = [
            (
                await env.client.get(f"{API}/accounts", headers=_bearer(token))
            ).status_code
            for _ in range(4)
        ]
        assert codes == [200, 200, 200, 429]
        # Лимит — на подключение, соседнее не страдает.
        r = await env.client.get(f"{API}/accounts", headers=_bearer(other))
        assert r.status_code == 200
        # И сайт тоже.
        r = await env.client.get(f"{API}/accounts", headers=env.site)
        assert r.status_code == 200


async def test_audit_line_without_query_or_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.read"])
        caplog.set_level(logging.INFO, logger="anfinances.ai_audit")
        await env.client.get(
            f"{API}/transactions?search=secret", headers=_bearer(token)
        )
        await env.client.delete(
            f"{API}/goals/00000000-0000-0000-0000-000000000001",
            headers=_bearer(token),
        )
        lines = [
            rec.getMessage()
            for rec in caplog.records
            if rec.name == "anfinances.ai_audit"
        ]
        assert len(lines) == 2
        assert lines[0].startswith("ai_access connection=")
        assert lines[0].endswith(f"GET {API}/transactions 200")
        assert "secret" not in lines[0]
        assert token not in " ".join(lines)
        # Удаление отклонено ещё до проверки токена — подключение
        # неизвестно, но запрос всё равно в аудите.
        assert lines[1].endswith("403")
        # Запросы сайта в аудит ИИ не попадают.
        caplog.clear()
        await env.client.get(f"{API}/accounts", headers=env.site)
        assert not [
            r for r in caplog.records if r.name == "anfinances.ai_audit"
        ]


def test_scopes_write_implies_read() -> None:
    assert normalize_scopes(["finance.write"]) == (
        "finance.read",
        "finance.write",
    )
    assert parse_scopes("finance.read finance.read") == ("finance.read",)
    with pytest.raises(InvalidScopeError):
        parse_scopes("finance.read admin")


def test_policy_examples() -> None:
    read = ("finance.read",)
    write = ("finance.read", "finance.write")
    p = "/api/v1"
    assert deny_reason("GET", f"{p}/accounts", read, p) is None
    assert deny_reason("POST", f"{p}/transactions", write, p) is None
    assert deny_reason("POST", f"{p}/transactions", read, p)
    assert deny_reason("DELETE", f"{p}/transactions/{{tx_id}}", write, p)
    assert deny_reason("GET", f"{p}/auth/me", read, p) is None
    assert deny_reason("POST", f"{p}/auth/logout", write, p)
    assert deny_reason("GET", f"{p}/auth/me/x", read, p)
    assert deny_reason("GET", f"{p}/users/me/currencies", read, p) is None
    assert deny_reason("PUT", f"{p}/users/me/currencies", write, p)
    assert deny_reason("GET", f"{p}/ai/whoami", read, p) is None
    assert deny_reason("GET", f"{p}/ai/connections", write, p)
    assert deny_reason(
        "POST", f"{p}/accounts/{{account_id}}/restore", write, p
    )
    assert deny_reason("OPTIONS", f"{p}/accounts", write, p)


def test_pkce_s256() -> None:
    verifier, challenge = pkce_pair()
    assert pkce_matches(verifier, challenge)
    assert not pkce_matches(verifier + "x", challenge)
