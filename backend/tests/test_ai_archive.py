"""Архив счетов и кредитов через токен ИИ — на настоящем приложении.

Ассистенту архив открыт, но только безопасный: счёт с нулевым
остатком и погашенный кредит. Всё, что убрало бы деньги или долг из
капитала, остаётся решением человека на сайте. И у счёта, и у
кредита есть обратный путь — /restore.
"""

import uuid
from decimal import Decimal

from app.core.enums import AccountType
from app.domains.accounts.models import Account
from app.domains.credits.models import Credit
from tests.ai_support import API, AiEnv, ai_env


async def _account(env: AiEnv, balance: str) -> uuid.UUID:
    async with env.sessionmaker() as session:
        account = Account(
            user_id=env.user_id,
            name=f"Счёт {uuid.uuid4().hex[:6]}",
            type=AccountType.SAVINGS,
            currency_code="RUB",
            initial_balance=Decimal(balance),
        )
        session.add(account)
        await session.commit()
        return account.id


async def _credit(env: AiEnv, balance: str) -> uuid.UUID:
    async with env.sessionmaker() as session:
        credit = Credit(
            user_id=env.user_id,
            name="Т-Банк",
            currency_code="RUB",
            principal_initial=Decimal("745000"),
            principal_balance=Decimal(balance),
        )
        session.add(credit)
        await session.commit()
        return credit.id


async def _writer(env: AiEnv) -> dict[str, str]:
    token = await env.personal_token(["finance.write"])
    return {"Authorization": f"Bearer {token}"}


async def test_empty_account_is_archived_and_restored() -> None:
    async with ai_env() as env:
        ai = await _writer(env)
        account_id = await _account(env, "0")

        r = await env.client.delete(f"{API}/accounts/{account_id}", headers=ai)
        assert r.status_code == 200, r.text
        r = await env.client.post(
            f"{API}/accounts/{account_id}/restore", headers=ai
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["is_archived"] is False


async def test_account_with_money_stays_with_the_human() -> None:
    async with ai_env() as env:
        ai = await _writer(env)
        account_id = await _account(env, "18000")
        url = f"{API}/accounts/{account_id}"

        plain = await env.client.delete(url, headers=ai)
        forced = await env.client.delete(
            url, params={"force": "true"}, headers=ai
        )
        human = await env.client.delete(
            url, params={"force": "true"}, headers=env.site
        )

        assert plain.status_code == 422
        assert forced.status_code == 403
        assert "остатком" in forced.json()["message"]
        assert human.status_code == 200, human.text


async def test_credit_with_debt_is_not_archived_by_assistant() -> None:
    async with ai_env() as env:
        ai = await _writer(env)
        credit_id = await _credit(env, "420527.66")
        url = f"{API}/credits/{credit_id}"

        refused = await env.client.delete(url, headers=ai)
        human = await env.client.delete(url, headers=env.site)

        assert refused.status_code == 422
        assert "остаток долга" in refused.json()["message"]
        assert human.status_code == 200, human.text


async def test_paid_off_credit_is_archived_and_restored() -> None:
    async with ai_env() as env:
        ai = await _writer(env)
        credit_id = await _credit(env, "0")

        r = await env.client.delete(f"{API}/credits/{credit_id}", headers=ai)
        assert r.status_code == 200, r.text

        active = await env.client.get(f"{API}/credits", headers=ai)
        every = await env.client.get(
            f"{API}/credits",
            params={"include_archived": "true"},
            headers=ai,
        )
        assert [c["id"] for c in active.json()["data"]] == []
        (archived,) = every.json()["data"]
        assert archived["is_archived"] is True

        r = await env.client.post(
            f"{API}/credits/{credit_id}/restore", headers=ai
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["is_archived"] is False


async def test_read_token_cannot_archive() -> None:
    async with ai_env() as env:
        token = await env.personal_token(["finance.read"])
        account_id = await _account(env, "0")

        r = await env.client.delete(
            f"{API}/accounts/{account_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert r.status_code == 403
        assert "только на чтение" in r.json()["message"]
