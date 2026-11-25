"""Краевые входы дают 4xx, а не 500.

Аудит 25.11.2026 нашёл пути к голому 500: явный null в PATCH,
месяц «2026-13», сумма шире Numeric(18, 4), ошибка базы без
обработчика. Здесь — по одному представителю каждого.
"""

import uuid
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import DataError, IntegrityError

from app.core.exceptions import register_exception_handlers
from app.domains.accounts.schemas import AccountUpdate
from app.domains.budgets.schemas import BudgetCreate
from app.domains.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
)
from tests.ai_support import API, ai_env


def _expense(amount: str) -> TransactionCreate:
    return TransactionCreate.model_validate(
        {
            "account_id": str(uuid.uuid4()),
            "kind": "expense",
            "amount": amount,
            "date": "2026-11-25T12:00:00+03:00",
        }
    )


def test_money_fits_the_column() -> None:
    assert _expense("1250.5").amount == Decimal("1250.5")
    with pytest.raises(ValidationError):
        _expense("0.00004")  # 5 знаков — база округлила бы до нуля
    with pytest.raises(ValidationError):
        _expense("1" + "0" * 15)  # 10¹⁵ не влезает в Numeric(18, 4)


def test_explicit_null_is_refused_but_omission_is_fine() -> None:
    assert TransactionUpdate.model_validate({"comment": None}).comment is None
    with pytest.raises(ValidationError, match="amount"):
        TransactionUpdate.model_validate({"amount": None})
    with pytest.raises(ValidationError, match="name"):
        AccountUpdate.model_validate({"name": None})
    # Необязательное поле очистить можно.
    assert AccountUpdate.model_validate({"comments": None}).comments is None


def test_month_must_exist() -> None:
    cat = str(uuid.uuid4())
    BudgetCreate.model_validate(
        {"month": "2026-12", "category_id": cat, "planned": "1"}
    )
    for bad in ("2026-13", "2026-00"):
        with pytest.raises(ValidationError):
            BudgetCreate.model_validate(
                {"month": bad, "category_id": cat, "planned": "1"}
            )


async def test_month_query_is_validated_on_routes() -> None:
    async with ai_env() as env:
        r = await env.client.get(
            f"{API}/budgets", params={"month": "2026-13"}, headers=env.site
        )
        assert r.status_code == 422, r.text


async def test_database_errors_become_client_errors() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/integrity")
    async def _integrity() -> None:
        raise IntegrityError("INSERT …", {"secret": "x"}, Exception("dup"))

    @app.get("/data")
    async def _data() -> None:
        raise DataError("INSERT …", {}, Exception("numeric overflow"))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as client:
        conflict = await client.get("/integrity")
        overflow = await client.get("/data")

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"
    assert "secret" not in conflict.text
    assert overflow.status_code == 422
