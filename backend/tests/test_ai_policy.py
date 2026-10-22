"""Политика доступа токенов ИИ — по настоящей таблице роутов.

Тест обходит все роуты приложения, а не список, написанный руками:
новый эндпоинт сразу попадает под проверку, и если он окажется
открыт для удаления или записи с токеном «только чтение», тест
упадёт.

Ожидания здесь записаны независимо от app.domains.ai.policy —
иначе тест проверял бы политику ею же самой.
"""

import re
import uuid

from fastapi.routing import APIRoute

from tests.ai_support import API, AiEnv, ai_env, make_settings

# Обход шлёт под сотню запросов одним токеном — лимит не про это.
_NO_LIMIT = {"ai_rate_limit_per_minute": 0}

# Протокол OAuth: клиент ходит туда без Bearer, токен ИИ в
# заголовке там ни на что не влияет.
_PROTOCOL = {
    f"{API}/ai/oauth/token",
    f"{API}/ai/oauth/revoke",
    f"{API}/ai/oauth/register",
    "/.well-known/oauth-authorization-server",
}

_DENY_ANY_METHOD_PREFIXES = (f"{API}/auth", f"{API}/import", f"{API}/ai")
_DENY_ANY_METHOD_PATHS = {
    f"{API}/export/all.json",
    f"{API}/currencies/rates/refresh",
}


def _routes(env: AiEnv) -> list[tuple[str, str]]:
    result = []
    for route in env.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in _PROTOCOL:
            continue
        for method in sorted(route.methods):
            result.append((method, route.path))
    assert len(result) > 50  # таблица роутов действительно обошлась
    return result


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def _denylisted(method: str, path: str) -> bool:
    under = any(
        path == p or path.startswith(p + "/")
        for p in _DENY_ANY_METHOD_PREFIXES
    )
    if under:
        # Единственные открытые чтения: whoami и профиль (/auth/me).
        allowed = {f"{API}/ai/whoami", f"{API}/auth/me"}
        return path not in allowed or method != "GET"
    if path in _DENY_ANY_METHOD_PATHS:
        return True
    if path.endswith(("/restore", "/archive")):
        return True
    # Закрыть сверку — решение человека; /reconcile/preview открыт.
    if path.endswith("/reconcile") and method != "GET":
        return True
    users_me = f"{API}/users/me"
    return (
        path == users_me or path.startswith(users_me + "/")
    ) and method != "GET"


async def _call(env: AiEnv, method: str, path: str, token: str) -> int:
    body = {} if method in {"POST", "PUT", "PATCH"} else None
    r = await env.client.request(
        method,
        _concrete(path),
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    return r.status_code


async def test_write_token_refused_on_delete_and_denylist() -> None:
    async with ai_env(make_settings(**_NO_LIMIT)) as env:
        token = await env.personal_token(["finance.write"])
        checked = 0
        for method, path in _routes(env):
            if method == "DELETE" or _denylisted(method, path):
                status = await _call(env, method, path, token)
                assert status == 403, (method, path, status)
                checked += 1
        assert checked > 15


async def test_read_token_refused_on_every_non_get() -> None:
    async with ai_env(make_settings(**_NO_LIMIT)) as env:
        token = await env.personal_token(["finance.read"])
        checked = 0
        for method, path in _routes(env):
            if method in {"GET", "HEAD"}:
                continue
            status = await _call(env, method, path, token)
            assert status == 403, (method, path, status)
            checked += 1
        assert checked > 30


async def test_write_token_can_reach_allowed_writes() -> None:
    # Обратная сторона: всё, что не запрещено, токену записи
    # открыто — 403 нигде, кроме запрещённого.
    async with ai_env(make_settings(**_NO_LIMIT)) as env:
        token = await env.personal_token(["finance.write"])
        for method, path in _routes(env):
            if method == "DELETE" or _denylisted(method, path):
                continue
            status = await _call(env, method, path, token)
            assert status != 403, (method, path, status)


async def test_read_token_reads_and_cannot_write() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.read"])
        auth = {"Authorization": f"Bearer {token}"}
        r = await env.client.get(f"{API}/accounts", headers=auth)
        assert r.status_code == 200, r.text
        r = await env.client.post(
            f"{API}/accounts",
            json={"name": "Карта", "type": "card", "currency_code": "RUB"},
            headers=auth,
        )
        assert r.status_code == 403
        assert "только на чтение" in r.json()["message"]


async def test_ai_token_cannot_manage_connections() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.write"])
        auth = {"Authorization": f"Bearer {token}"}
        r = await env.client.get(f"{API}/ai/connections", headers=auth)
        assert r.status_code == 403
        r = await env.client.post(
            f"{API}/ai/connections",
            json={"name": "ещё", "scopes": ["finance.write"]},
            headers=auth,
        )
        assert r.status_code == 403


async def test_site_jwt_keeps_full_access() -> None:
    async with ai_env() as env:
        r = await env.client.get(f"{API}/auth/me", headers=env.site)
        assert r.status_code == 200
        r = await env.client.get(f"{API}/export/all.json", headers=env.site)
        assert r.status_code == 200
