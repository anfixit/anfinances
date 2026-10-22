"""OAuth 2.1 для ИИ-ассистентов: метаданные, DCR, CIMD, согласие,
обмен кода, ротация refresh, отзыв."""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.config import PredefinedAiClient
from app.domains.ai.clients import (
    ClientMetadataError,
    HttpxMetadataFetcher,
    is_allowed_dcr_redirect,
    is_safe_redirect_uri,
)
from app.domains.ai.models import AiConnection
from tests.ai_support import (
    API,
    CLAUDE_REDIRECT,
    RESOURCE,
    AiEnv,
    FakeFetcher,
    ai_env,
    make_settings,
    pkce_pair,
)

ISSUER = "https://anfinances.ru"
CIMD_URL = "https://claude.ai/oauth/mcp-oauth-client-metadata"
CIMD_DOC = {
    "client_id": CIMD_URL,
    "client_name": "Claude",
    "redirect_uris": [CLAUDE_REDIRECT],
    "token_endpoint_auth_method": "none",
}


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def _register(env: AiEnv, uris: list[str]) -> str:
    r = await env.client.post(
        f"{API}/ai/oauth/register",
        json={"client_name": "Claude Code", "redirect_uris": uris},
    )
    assert r.status_code == 201, r.text
    client_id: str = r.json()["client_id"]
    return client_id


def _params(
    client_id: str,
    challenge: str,
    redirect_uri: str = CLAUDE_REDIRECT,
    **over: str,
) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "finance.read finance.write",
        "state": "st-123",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    }
    params.update(over)
    return params


async def _check(env: AiEnv, params: dict[str, str]) -> dict[str, Any]:
    r = await env.client.get(
        f"{API}/ai/oauth/authorize/check", params=params, headers=env.site
    )
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()["data"]
    return data


async def _approve(
    env: AiEnv, params: dict[str, str], scopes: list[str]
) -> str:
    r = await env.client.post(
        f"{API}/ai/oauth/authorize/approve",
        json={**params, "scopes": scopes},
        headers=env.site,
    )
    assert r.status_code == 200, r.text
    redirect: str = r.json()["data"]["redirect_to"]
    return redirect


async def _token(env: AiEnv, **form: str) -> httpx.Response:
    return await env.client.post(f"{API}/ai/oauth/token", data=form)


async def _authorize(
    env: AiEnv, client_id: str, scopes: list[str] | None = None
) -> tuple[str, str]:
    verifier, challenge = pkce_pair()
    params = _params(client_id, challenge)
    redirect = await _approve(
        env, params, scopes or ["finance.read", "finance.write"]
    )
    return _query(redirect)["code"], verifier


async def _full_flow(env: AiEnv, client_id: str) -> dict[str, Any]:
    code, verifier = await _authorize(env, client_id)
    r = await _token(
        env,
        grant_type="authorization_code",
        code=code,
        code_verifier=verifier,
        client_id=client_id,
        redirect_uri=CLAUDE_REDIRECT,
        resource=RESOURCE,
    )
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


# ── Метаданные ───────────────────────────────────────────────────────


async def test_metadata_at_root() -> None:
    async with ai_env() as env:
        r = await env.client.get("/.well-known/oauth-authorization-server")
        assert r.status_code == 200
        meta = r.json()
        assert meta["issuer"] == ISSUER
        assert meta["authorization_endpoint"] == f"{ISSUER}/oauth/authorize"
        assert meta["token_endpoint"] == f"{ISSUER}{API}/ai/oauth/token"
        assert meta["revocation_endpoint"] == f"{ISSUER}{API}/ai/oauth/revoke"
        assert (
            meta["registration_endpoint"] == f"{ISSUER}{API}/ai/oauth/register"
        )
        assert meta["code_challenge_methods_supported"] == ["S256"]
        assert meta["token_endpoint_auth_methods_supported"] == ["none"]
        assert meta["scopes_supported"] == ["finance.read", "finance.write"]
        assert meta["client_id_metadata_document_supported"] is True
        assert meta["authorization_response_iss_parameter_supported"] is True


async def test_metadata_follows_public_origin() -> None:
    settings = make_settings(public_origin="https://fin.example.org/")
    async with ai_env(settings) as env:
        meta = (
            await env.client.get("/.well-known/oauth-authorization-server")
        ).json()
        assert meta["issuer"] == "https://fin.example.org"
        assert settings.ai_resource == "https://fin.example.org/mcp"


# ── Динамическая регистрация ─────────────────────────────────────────


async def test_dcr_allows_only_listed_hosts() -> None:
    async with ai_env() as env:
        ok = await _register(
            env, [CLAUDE_REDIRECT, "http://localhost:33418/callback"]
        )
        assert ok.startswith("anf_dcr_")
        for uris in (
            ["https://evil.example/cb"],
            ["http://claude.ai/cb"],
            ["https://claude.ai.evil.example/cb"],
            ["https://claude.ai/cb#frag"],
            ["https://user@claude.ai/cb"],
            ["http://192.168.1.5:8000/cb"],
            [],
        ):
            r = await env.client.post(
                f"{API}/ai/oauth/register",
                json={"client_name": "x", "redirect_uris": uris},
            )
            assert r.status_code == 400, uris
            assert r.json()["error"] == "invalid_redirect_uri"
        r = await env.client.post(
            f"{API}/ai/oauth/register",
            json={
                "redirect_uris": [CLAUDE_REDIRECT],
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_client_metadata"
        r = await env.client.post(f"{API}/ai/oauth/register", content=b"{")
        assert r.status_code == 400


def test_redirect_uri_rules() -> None:
    s = make_settings()
    assert is_safe_redirect_uri("http://127.0.0.1:5555/cb")
    assert not is_safe_redirect_uri("http://example.com/cb")
    assert not is_safe_redirect_uri("javascript:alert(1)")
    assert is_allowed_dcr_redirect("https://chatgpt.com/cb", s)
    assert not is_allowed_dcr_redirect("https://chatgpt.com:8443/cb", s)
    assert not is_allowed_dcr_redirect("https://openai.com/cb", s)


# ── Полный поток ─────────────────────────────────────────────────────


async def test_full_flow_with_dcr_client() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        verifier, challenge = pkce_pair()
        params = _params(client_id, challenge)

        check = await _check(env, params)
        assert check["status"] == "ok"
        assert check["client_name"] == "Claude Code"
        assert check["redirect_host"] == "claude.ai"
        assert check["scopes"] == ["finance.read", "finance.write"]
        deny = _query(check["deny_redirect_to"])
        assert deny == {
            "error": "access_denied",
            "error_description": "The user denied access",
            "state": "st-123",
            "iss": ISSUER,
        }

        redirect = await _approve(env, params, ["finance.read"])
        assert redirect.startswith(CLAUDE_REDIRECT + "?")
        q = _query(redirect)
        assert q["state"] == "st-123"
        assert q["iss"] == ISSUER

        r = await _token(
            env,
            grant_type="authorization_code",
            code=q["code"],
            code_verifier=verifier,
            client_id=client_id,
            redirect_uri=CLAUDE_REDIRECT,
            resource=RESOURCE + "/",
        )
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        tokens = r.json()
        assert tokens["token_type"] == "Bearer"
        assert tokens["expires_in"] == 3600
        # Пользователь снял галочку записи — выдано только чтение.
        assert tokens["scope"] == "finance.read"
        assert tokens["access_token"].startswith("anf_oat_")
        assert tokens["refresh_token"].startswith("anf_ort_")

        auth = {"Authorization": f"Bearer {tokens['access_token']}"}
        who = (await env.client.get(f"{API}/ai/whoami", headers=auth)).json()
        assert who["data"]["kind"] == "oauth"
        assert who["data"]["name"] == "Claude Code"
        assert who["data"]["client_id"] == client_id
        assert who["data"]["resource"] == RESOURCE
        assert who["data"]["expires_at"] is not None
        r = await env.client.post(
            f"{API}/accounts",
            json={"name": "Карта", "type": "card", "currency_code": "RUB"},
            headers=auth,
        )
        assert r.status_code == 403

        # Refresh-токен как Bearer не годится.
        r = await env.client.get(
            f"{API}/accounts",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )
        assert r.status_code == 401

        r = await env.client.get(f"{API}/ai/connections", headers=env.site)
        listed = r.json()["data"]
        assert [c["kind"] for c in listed] == ["oauth"]


async def test_code_is_single_use_and_reuse_revokes() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        code, verifier = await _authorize(env, client_id)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": CLAUDE_REDIRECT,
        }
        first = await _token(env, **form)
        assert first.status_code == 200
        again = await _token(env, **form)
        assert again.status_code == 400
        assert again.json()["error"] == "invalid_grant"
        # Выданное по коду подключение отозвано.
        access = first.json()["access_token"]
        r = await env.client.get(
            f"{API}/ai/whoami", headers={"Authorization": f"Bearer {access}"}
        )
        assert r.status_code == 401


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("code_verifier", "x" * 50, "invalid_grant"),
        ("client_id", "anf_dcr_other", "invalid_grant"),
        ("redirect_uri", CLAUDE_REDIRECT + "/x", "invalid_grant"),
        ("resource", "https://anfinances.ru/other", "invalid_target"),
        ("code", "nope", "invalid_grant"),
    ],
)
async def test_code_exchange_checks_binding(
    field: str, value: str, error: str
) -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        code, verifier = await _authorize(env, client_id)
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": CLAUDE_REDIRECT,
        }
        form[field] = value
        r = await _token(env, **form)
        assert r.status_code == 400
        assert r.json()["error"] == error


async def test_token_endpoint_errors() -> None:
    async with ai_env() as env:
        r = await _token(env)
        assert r.json()["error"] == "invalid_request"
        r = await _token(env, grant_type="password")
        assert r.json()["error"] == "unsupported_grant_type"
        r = await _token(env, grant_type="authorization_code")
        assert r.json()["error"] == "invalid_request"
        r = await env.client.post(
            f"{API}/ai/oauth/token",
            content="grant_type=refresh_token&grant_type=refresh_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.json()["error"] == "invalid_request"


async def test_refresh_rotation_and_reuse_detection() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        tokens = await _full_flow(env, client_id)
        old = tokens["refresh_token"]

        r = await _token(
            env,
            grant_type="refresh_token",
            refresh_token=old,
            client_id=client_id,
        )
        assert r.status_code == 200, r.text
        new = r.json()
        assert new["refresh_token"] != old
        assert new["scope"] == "finance.read finance.write"

        # Чужой client_id не может обновить.
        r = await _token(
            env,
            grant_type="refresh_token",
            refresh_token=new["refresh_token"],
            client_id="anf_dcr_x",
        )
        assert r.json()["error"] == "invalid_grant"

        # Старый refresh предъявлен снова — подключение отзывается.
        r = await _token(
            env,
            grant_type="refresh_token",
            refresh_token=old,
            client_id=client_id,
        )
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"
        r = await _token(
            env,
            grant_type="refresh_token",
            refresh_token=new["refresh_token"],
            client_id=client_id,
        )
        assert r.status_code == 400
        auth = {"Authorization": f"Bearer {new['access_token']}"}
        r = await env.client.get(f"{API}/ai/whoami", headers=auth)
        assert r.status_code == 401


async def test_refresh_cannot_widen_scope() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        code, verifier = await _authorize(env, client_id, ["finance.read"])
        tokens = (
            await _token(
                env,
                grant_type="authorization_code",
                code=code,
                code_verifier=verifier,
                client_id=client_id,
                redirect_uri=CLAUDE_REDIRECT,
            )
        ).json()
        r = await _token(
            env,
            grant_type="refresh_token",
            refresh_token=tokens["refresh_token"],
            client_id=client_id,
            scope="finance.write",
        )
        assert r.json()["error"] == "invalid_scope"


async def test_revocation_endpoint() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        tokens = await _full_flow(env, client_id)
        auth = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Неизвестный токен — тоже 200, без подсказок.
        r = await env.client.post(
            f"{API}/ai/oauth/revoke", data={"token": "anf_ort_unknown"}
        )
        assert r.status_code == 200
        # Чужой клиент не отзывает не своё.
        r = await env.client.post(
            f"{API}/ai/oauth/revoke",
            data={"token": tokens["refresh_token"], "client_id": "other"},
        )
        assert r.status_code == 200
        assert (
            await env.client.get(f"{API}/ai/whoami", headers=auth)
        ).status_code == 200

        r = await env.client.post(
            f"{API}/ai/oauth/revoke",
            data={"token": tokens["refresh_token"], "client_id": client_id},
        )
        assert r.status_code == 200
        r = await env.client.get(f"{API}/ai/whoami", headers=auth)
        assert r.status_code == 401
        async with env.sessionmaker() as s:
            conn = (await s.execute(select(AiConnection))).scalar_one()
            assert conn.revoked_at is not None

        r = await env.client.post(f"{API}/ai/oauth/revoke", data={})
        assert r.status_code == 400


# ── Ошибки авторизации ───────────────────────────────────────────────


async def test_unverified_client_or_redirect_is_not_redirected() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        for params in (
            _params("anf_dcr_unknown", challenge),
            _params(client_id, challenge, "https://evil.example/cb"),
            _params(client_id, challenge, CLAUDE_REDIRECT + "/"),
            {
                k: v
                for k, v in _params(client_id, challenge).items()
                if k != "client_id"
            },
        ):
            data = await _check(env, params)
            assert data["status"] == "error", params
            assert data["redirect_to"] is None
            assert data["message"]
            r = await env.client.post(
                f"{API}/ai/oauth/authorize/approve",
                json={**params, "scopes": ["finance.read"]},
                headers=env.site,
            )
            assert r.status_code == 422


@pytest.mark.parametrize(
    ("over", "error"),
    [
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"code_challenge": ""}, "invalid_request"),
        ({"response_type": "token"}, "unsupported_response_type"),
        ({"resource": "https://anfinances.ru/api"}, "invalid_target"),
        ({"resource": ""}, "invalid_target"),
        ({"scope": "finance.admin"}, "invalid_scope"),
    ],
)
async def test_redirectable_errors_carry_state_and_iss(
    over: dict[str, str], error: str
) -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        params = _params(client_id, challenge, **over)
        data = await _check(env, params)
        assert data["status"] == "error"
        assert data["error"] == error
        q = _query(data["redirect_to"])
        assert q["error"] == error
        assert q["state"] == "st-123"
        assert q["iss"] == ISSUER
        assert data["redirect_to"].startswith(CLAUDE_REDIRECT + "?")


async def test_missing_scope_requests_everything() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        params = _params(client_id, challenge)
        del params["scope"]
        data = await _check(env, params)
        assert data["scopes"] == ["finance.read", "finance.write"]


async def test_cannot_grant_more_than_requested() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        params = _params(client_id, challenge, scope="finance.read")
        r = await env.client.post(
            f"{API}/ai/oauth/authorize/approve",
            json={**params, "scopes": ["finance.write"]},
            headers=env.site,
        )
        assert r.status_code == 422


async def test_consent_requires_site_login() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        r = await env.client.get(
            f"{API}/ai/oauth/authorize/check",
            params=_params(client_id, challenge),
        )
        assert r.status_code == 401


# ── CIMD и заранее заведённые клиенты ────────────────────────────────


async def test_cimd_client() -> None:
    fetcher = FakeFetcher({CIMD_URL: CIMD_DOC})
    async with ai_env(fetcher=fetcher) as env:
        _, challenge = pkce_pair()
        data = await _check(env, _params(CIMD_URL, challenge))
        assert data["status"] == "ok", data
        assert data["client_name"] == "Claude"
        tokens = await _full_flow(env, CIMD_URL)
        assert tokens["access_token"].startswith("anf_oat_")
        # Документ кешируется: проверка, одобрение — одна загрузка.
        assert fetcher.calls == [CIMD_URL]


async def test_cimd_rejections() -> None:
    evil = "https://evil.example/client.json"
    mismatched = "https://chatgpt.com/oauth/client.json"
    fetcher = FakeFetcher(
        {
            evil: {**CIMD_DOC, "client_id": evil},
            mismatched: {**CIMD_DOC, "client_id": CIMD_URL},
        }
    )
    async with ai_env(fetcher=fetcher) as env:
        _, challenge = pkce_pair()
        for client_id in (evil, mismatched, "https://claude.ai/missing"):
            data = await _check(env, _params(client_id, challenge))
            assert data["status"] == "error", client_id
            assert data["redirect_to"] is None
        # Хост не из списка — документ даже не скачивается.
        assert evil not in fetcher.calls
        data = await _check(
            env,
            _params(CIMD_URL, challenge, "https://claude.ai/other"),
        )
        assert data["status"] == "error"


async def test_predefined_client() -> None:
    settings = make_settings(
        ai_predefined_clients=[
            PredefinedAiClient(
                client_id="my-cli",
                name="Мой скрипт",
                redirect_uris=["http://127.0.0.1:8765/cb"],
            )
        ]
    )
    async with ai_env(settings) as env:
        _, challenge = pkce_pair()
        data = await _check(
            env, _params("my-cli", challenge, "http://127.0.0.1:8765/cb")
        )
        assert data["status"] == "ok"
        assert data["client_name"] == "Мой скрипт"


# ── Загрузчик документа клиента ──────────────────────────────────────


async def test_fetcher_refuses_cross_host_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        if request.url.path == "/b":
            return httpx.Response(
                302, headers={"location": "https://evil.example/c"}
            )
        return httpx.Response(200, json={})

    fetcher = HttpxMetadataFetcher(
        make_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ClientMetadataError):
        await fetcher.fetch("https://claude.ai/a")


async def test_fetcher_limits_size() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (65 * 1024))

    fetcher = HttpxMetadataFetcher(
        make_settings(), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ClientMetadataError):
        await fetcher.fetch("https://claude.ai/a")


async def test_fetcher_follows_same_host_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(301, headers={"location": "/b"})
        return httpx.Response(200, content=b'{"ok": true}')

    fetcher = HttpxMetadataFetcher(
        make_settings(), transport=httpx.MockTransport(handler)
    )
    assert await fetcher.fetch("https://claude.ai/a") == b'{"ok": true}'


# ── Требования ChatGPT и Claude ──────────────────────────────────────


async def test_metadata_has_no_extra_scopes() -> None:
    async with ai_env() as env:
        meta = (
            await env.client.get("/.well-known/oauth-authorization-server")
        ).json()
        assert meta["issuer"] == "https://anfinances.ru"
        assert "openid" not in meta["scopes_supported"]
        assert "offline_access" not in meta["scopes_supported"]


async def test_chatgpt_redirects_registrable() -> None:
    async with ai_env() as env:
        await _register(
            env,
            [
                "https://chatgpt.com/connector_platform_oauth_redirect",
                "https://chatgpt.com/connector/oauth/abc123",
            ],
        )


async def test_loopback_redirect_ignores_port_only() -> None:
    async with ai_env() as env:
        client_id = await _register(env, ["http://localhost:33418/callback"])
        _, challenge = pkce_pair()
        ok = await _check(
            env,
            _params(client_id, challenge, "http://localhost:5555/callback"),
        )
        assert ok["status"] == "ok", ok
        for uri in (
            "http://localhost:5555/other",
            "http://127.0.0.1:5555/callback",
            "https://localhost:5555/callback",
        ):
            bad = await _check(env, _params(client_id, challenge, uri))
            assert bad["status"] == "error", uri
            assert bad["redirect_to"] is None


async def test_offline_access_is_tolerated() -> None:
    async with ai_env() as env:
        client_id = await _register(env, [CLAUDE_REDIRECT])
        _, challenge = pkce_pair()
        data = await _check(
            env,
            _params(client_id, challenge, scope="finance.read offline_access"),
        )
        assert data["status"] == "ok"
        assert data["scopes"] == ["finance.read"]
