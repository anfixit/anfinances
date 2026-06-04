"""Тесты HIBP-проверки (без реальной сети, MockTransport)."""

import hashlib

import httpx
import pytest

from app.config import Settings
from app.core.pwned import HibpChecker, PwnedError


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {"secret_key": "x" * 64}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _factory(handler: httpx.MockTransport):
    def make() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=handler, timeout=1.0)

    return make


def _ok_handler(body: str) -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(200, text=body))


def _error_handler() -> httpx.MockTransport:
    def raise_err(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    return httpx.MockTransport(raise_err)


async def test_pwned_password_rejected() -> None:
    plain = "password12345678"
    suffix = hashlib.sha1(plain.encode()).hexdigest()[5:].upper()
    transport = _ok_handler(f"{suffix}:42\nAAAA:1")
    checker = HibpChecker(_settings(), _factory(transport))
    with pytest.raises(PwnedError):
        await checker.assert_not_pwned(plain)


async def test_clean_password_ok() -> None:
    transport = _ok_handler("AAAA:1\nBBBB:2")
    checker = HibpChecker(_settings(), _factory(transport))
    await checker.assert_not_pwned("unique-strong-xyz")


async def test_disabled_skips() -> None:
    checker = HibpChecker(_settings(hibp_enabled=False))
    await checker.assert_not_pwned("anything")


async def test_fail_open_on_network_error() -> None:
    checker = HibpChecker(
        _settings(hibp_fail_open=True), _factory(_error_handler())
    )
    await checker.assert_not_pwned("whatever-strong-1")


async def test_fail_closed_on_network_error() -> None:
    checker = HibpChecker(
        _settings(hibp_fail_open=False),
        _factory(_error_handler()),
    )
    with pytest.raises(PwnedError):
        await checker.assert_not_pwned("whatever-strong-1")
