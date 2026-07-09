"""Юнит-тесты CreditService."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums import AccountType
from app.core.exceptions import (
    AlreadyExistsError,
    NotFoundError,
    ValidationFailedError,
)
from app.domains.accounts.models import Account
from app.domains.credits.models import Credit, CreditPayment
from app.domains.credits.schemas import CreditCreate, CreditUpdate
from app.domains.credits.service import CreditService

USER = uuid.uuid4()
NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeCreditRepo:
    def __init__(self) -> None:
        self.credits: list[Credit] = []
        self.payments: list[CreditPayment] = []
        self.currencies = {"RUB", "USD"}

    async def list_active(self, user_id):
        return [
            credit
            for credit in self.credits
            if credit.user_id == user_id and not credit.is_archived
        ]

    async def get(self, credit_id, user_id):
        return next(
            (
                credit
                for credit in self.credits
                if credit.id == credit_id and credit.user_id == user_id
            ),
            None,
        )

    async def get_active_by_name(self, user_id, name):
        return next(
            (
                credit
                for credit in self.credits
                if credit.user_id == user_id
                and credit.name == name
                and not credit.is_archived
            ),
            None,
        )

    async def currency_exists(self, code):
        return code in self.currencies

    async def has_payments(self, credit_id, user_id):
        return any(
            payment.credit_id == credit_id and payment.user_id == user_id
            for payment in self.payments
        )

    async def add(self, credit):
        if credit.id is None:
            credit.id = uuid.uuid4()
        self.credits.append(credit)
        return credit


class FakeAccounts:
    def __init__(self, accounts):
        self._accounts = {account.id: account for account in accounts}

    async def get(self, account_id, user_id):
        account = self._accounts.get(account_id)
        if account is None or account.user_id != user_id:
            return None
        return account


def _account(code: str = "RUB") -> Account:
    return Account(
        id=uuid.uuid4(),
        user_id=USER,
        name=f"Счёт {code}",
        type=AccountType.CARD,
        currency_code=code,
        is_archived=False,
    )


def _create(**kwargs: object) -> CreditCreate:
    data: dict[str, object] = {
        "name": "Кредит Сбер",
        "currency_code": "rub",
        "principal_initial": Decimal("100000"),
        "annual_rate": Decimal("19.9"),
        "term_months": 24,
        "start_date": NOW.date(),
        "payment_day": 14,
    }
    data.update(kwargs)
    return CreditCreate(**data)


def _service(
    repo: FakeCreditRepo | None = None,
    accounts: list[Account] | None = None,
) -> tuple[CreditService, FakeCreditRepo]:
    credit_repo = repo or FakeCreditRepo()
    service = CreditService(credit_repo, FakeAccounts(accounts or []))
    return service, credit_repo


async def test_create_credit_sets_initial_balance() -> None:
    service, _ = _service()

    credit = await service.create_credit(USER, _create())

    assert credit.currency_code == "RUB"
    assert credit.principal_initial == Decimal("100000")
    assert credit.principal_balance == Decimal("100000")


async def test_create_credit_rejects_unknown_currency() -> None:
    service, _ = _service()

    with pytest.raises(ValidationFailedError):
        await service.create_credit(USER, _create(currency_code="XXX"))


async def test_create_credit_rejects_duplicate_active_name() -> None:
    service, _ = _service()
    await service.create_credit(USER, _create(name="A"))

    with pytest.raises(AlreadyExistsError):
        await service.create_credit(USER, _create(name="A"))


async def test_archive_credit_allows_name_reuse() -> None:
    service, _ = _service()
    first = await service.create_credit(USER, _create(name="A"))
    await service.archive_credit(first.id, USER)

    second = await service.create_credit(USER, _create(name="A"))

    assert second.id != first.id


async def test_linked_account_must_exist() -> None:
    service, _ = _service()

    with pytest.raises(NotFoundError):
        await service.create_credit(
            USER,
            _create(linked_account_id=uuid.uuid4()),
        )


async def test_linked_account_currency_must_match() -> None:
    account = _account("USD")
    service, _ = _service(accounts=[account])

    with pytest.raises(ValidationFailedError):
        await service.create_credit(
            USER,
            _create(linked_account_id=account.id),
        )


async def test_update_initial_principal_before_payments() -> None:
    service, _ = _service()
    credit = await service.create_credit(USER, _create())

    updated = await service.update_credit(
        credit.id,
        USER,
        CreditUpdate(principal_initial=Decimal("120000")),
    )

    assert updated.principal_initial == Decimal("120000")
    assert updated.principal_balance == Decimal("120000")


async def test_update_initial_principal_after_payments_rejected() -> None:
    service, repo = _service()
    credit = await service.create_credit(USER, _create())
    repo.payments.append(
        CreditPayment(
            id=uuid.uuid4(),
            user_id=USER,
            credit_id=credit.id,
            payment_account_id=uuid.uuid4(),
            date=NOW,
            total_amount=Decimal("1000"),
            principal_amount=Decimal("500"),
            interest_amount=Decimal("500"),
            fee_amount=Decimal("0"),
            currency_code="RUB",
        )
    )

    with pytest.raises(ValidationFailedError):
        await service.update_credit(
            credit.id,
            USER,
            CreditUpdate(principal_initial=Decimal("120000")),
        )
