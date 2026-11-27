"""Корзина — на настоящем приложении (SQLite), с сайта и от ИИ.

Строки кладутся прямо в базу: создание через сервисы тянуло бы курсы
валют и справочники, а проверяем мы удаление и возврат.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.enums import AccountType, TransactionKind
from app.domains.accounts.models import Account
from app.domains.credits.models import Credit, CreditPayment
from app.domains.transactions.models import Transaction, Transfer
from tests.ai_support import API, AiEnv, ai_env

DAY = datetime(2026, 11, 14, 7, 0, tzinfo=UTC)


async def _account(env: AiEnv, name: str = "Альфа") -> uuid.UUID:
    async with env.sessionmaker() as s:
        account = Account(
            user_id=env.user_id,
            name=name,
            type=AccountType.CARD,
            currency_code="RUB",
            initial_balance=Decimal("0"),
        )
        s.add(account)
        await s.commit()
        return account.id


def _tx(
    env: AiEnv,
    account_id: uuid.UUID,
    amount: str,
    kind: TransactionKind = TransactionKind.EXPENSE,
    **extra: object,
) -> Transaction:
    value = Decimal(amount)
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": env.user_id,
        "date": DAY,
        "kind": kind,
        "amount": value,
        "currency_code": "RUB",
        "amount_rub": value,
        "exchange_rate": Decimal("1"),
        "account_id": account_id,
        "account_name_snapshot": "Альфа",
    }
    fields.update(extra)
    return Transaction(**fields)


async def _add(env: AiEnv, *rows: object) -> None:
    async with env.sessionmaker() as s:
        for row in rows:
            s.add(row)
            await s.flush()
        await s.commit()


async def _get(env: AiEnv, model: type, row_id: uuid.UUID) -> object:
    async with env.sessionmaker() as s:
        return await s.get(model, row_id)


async def _ai(env: AiEnv) -> dict[str, str]:
    token = await env.personal_token(["finance.write"])
    return {"Authorization": f"Bearer {token}"}


async def test_deleted_transaction_returns_as_it_was() -> None:
    async with ai_env() as env:
        account = await _account(env)
        tx = _tx(env, account, "-431", comment="чехол")
        await _add(env, tx)

        r = await env.client.delete(
            f"{API}/transactions/{tx.id}", headers=env.site
        )
        assert r.status_code == 200, r.text
        trash_id = r.json()["data"]["trash_id"]
        assert await _get(env, Transaction, tx.id) is None

        listed = (
            await env.client.get(f"{API}/trash", headers=env.site)
        ).json()
        (item,) = listed["data"]
        assert item["id"] == trash_id
        assert item["source"] == "Сайт"
        assert "Трата 431,00 ₽" in item["summary"]
        assert "«чехол»" in item["summary"]

        r = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=env.site
        )
        assert r.status_code == 200, r.text
        back = await _get(env, Transaction, tx.id)
        assert isinstance(back, Transaction)
        assert back.amount == Decimal("-431")
        assert back.comment == "чехол"
        assert back.kind == TransactionKind.EXPENSE

        listed = (
            await env.client.get(f"{API}/trash", headers=env.site)
        ).json()
        assert listed["data"] == []
        again = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=env.site
        )
        assert again.status_code == 422


async def test_assistant_deletion_is_signed_and_restorable() -> None:
    async with ai_env() as env:
        ai = await _ai(env)
        account = await _account(env)
        tx = _tx(env, account, "-239")
        await _add(env, tx)

        r = await env.client.delete(f"{API}/transactions/{tx.id}", headers=ai)
        assert r.status_code == 200, r.text
        trash_id = r.json()["data"]["trash_id"]

        listed = (await env.client.get(f"{API}/trash", headers=ai)).json()
        assert listed["data"][0]["source"] == "ИИ: Тест"
        r = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=ai
        )
        assert r.status_code == 200, r.text
        assert await _get(env, Transaction, tx.id) is not None


async def test_assistant_leaves_reconciled_to_the_human() -> None:
    async with ai_env() as env:
        ai = await _ai(env)
        account = await _account(env)
        tx = _tx(env, account, "-100", reconciled_at=DAY)
        await _add(env, tx)

        refused = await env.client.delete(
            f"{API}/transactions/{tx.id}", headers=ai
        )
        human = await env.client.delete(
            f"{API}/transactions/{tx.id}", headers=env.site
        )

        assert refused.status_code == 403
        assert "сверена" in refused.json()["message"]
        assert human.status_code == 200, human.text


async def test_transfer_goes_to_trash_whole_and_comes_back_whole() -> None:
    async with ai_env() as env:
        ai = await _ai(env)
        alfa = await _account(env)
        ozon = await _account(env, "Озон")
        transfer = Transfer(id=uuid.uuid4(), user_id=env.user_id)
        out = _tx(
            env,
            alfa,
            "-4312.04",
            TransactionKind.TRANSFER,
            transfer_id=transfer.id,
            to_account_name_snapshot="Озон",
        )
        into = _tx(
            env,
            ozon,
            "4312.04",
            TransactionKind.TRANSFER,
            transfer_id=transfer.id,
            account_name_snapshot="Озон",
        )
        await _add(env, transfer, out, into)

        r = await env.client.delete(
            f"{API}/transfers/{transfer.id}", headers=ai
        )
        assert r.status_code == 200, r.text
        summary = r.json()["data"]["summary"]
        assert "Перевод Альфа → Озон: 4 312,04 ₽" in summary
        assert await _get(env, Transfer, transfer.id) is None
        assert await _get(env, Transaction, into.id) is None

        trash_id = r.json()["data"]["trash_id"]
        r = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=ai
        )
        assert r.status_code == 200, r.text
        async with env.sessionmaker() as s:
            legs = (
                (
                    await s.execute(
                        select(Transaction).where(
                            Transaction.transfer_id == transfer.id
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert sorted(leg.amount for leg in legs) == [
            Decimal("-4312.04"),
            Decimal("4312.04"),
        ]


async def _credit_with_payment(
    env: AiEnv,
) -> tuple[uuid.UUID, uuid.UUID]:
    account = await _account(env)
    credit = Credit(
        id=uuid.uuid4(),
        user_id=env.user_id,
        name="Т-Банк",
        currency_code="RUB",
        principal_initial=Decimal("745000"),
        principal_balance=Decimal("660000"),
    )
    tx = _tx(env, account, "-85000", TransactionKind.CREDIT_PAYMENT)
    payment = CreditPayment(
        id=uuid.uuid4(),
        user_id=env.user_id,
        credit_id=credit.id,
        payment_account_id=account,
        transaction_id=tx.id,
        date=DAY,
        total_amount=Decimal("85000"),
        principal_amount=Decimal("85000"),
        interest_amount=Decimal("0"),
        fee_amount=Decimal("0"),
        currency_code="RUB",
    )
    await _add(env, credit, tx, payment)
    return credit.id, payment.id


async def _balance(env: AiEnv, credit_id: uuid.UUID) -> Decimal:
    credit = await _get(env, Credit, credit_id)
    assert isinstance(credit, Credit)
    return credit.principal_balance


async def test_credit_payment_round_trip_moves_the_debt() -> None:
    async with ai_env() as env:
        ai = await _ai(env)
        credit_id, payment_id = await _credit_with_payment(env)
        url = f"{API}/credits/{credit_id}/payments/{payment_id}"

        r = await env.client.delete(url, headers=ai)
        assert r.status_code == 200, r.text
        assert "Платёж по кредиту «Т-Банк»" in r.json()["data"]["summary"]
        assert await _balance(env, credit_id) == Decimal("745000")

        trash_id = r.json()["data"]["trash_id"]
        r = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=ai
        )
        assert r.status_code == 200, r.text
        assert await _balance(env, credit_id) == Decimal("660000")
        assert await _get(env, CreditPayment, payment_id) is not None


async def test_payment_that_no_longer_fits_is_not_restored() -> None:
    async with ai_env() as env:
        credit_id, payment_id = await _credit_with_payment(env)
        r = await env.client.delete(
            f"{API}/credits/{credit_id}/payments/{payment_id}",
            headers=env.site,
        )
        trash_id = r.json()["data"]["trash_id"]
        # После удаления долг погасили по-другому — почти до нуля.
        async with env.sessionmaker() as s:
            credit = await s.get(Credit, credit_id)
            assert credit is not None
            credit.principal_balance = Decimal("1000")
            await s.commit()

        r = await env.client.post(
            f"{API}/trash/{trash_id}/restore", headers=env.site
        )

        assert r.status_code == 422
        assert "не помещается" in r.json()["message"]
        assert await _balance(env, credit_id) == Decimal("1000")


async def test_payment_must_belong_to_named_credit() -> None:
    async with ai_env() as env:
        _, payment_id = await _credit_with_payment(env)

        r = await env.client.delete(
            f"{API}/credits/{uuid.uuid4()}/payments/{payment_id}",
            headers=env.site,
        )

        assert r.status_code == 404
        assert await _get(env, CreditPayment, payment_id) is not None
