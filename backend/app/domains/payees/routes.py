"""HTTP-роуты получателей: /payees/*."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.datetime import month_bounds_utc
from app.core.dependencies import CurrentUser, DbSession
from app.core.schemas import ApiResponse
from app.domains.payees.repository import (
    PayeeRepository,
    SqlPayeeRepository,
)
from app.domains.payees.schemas import (
    PayeeCreate,
    PayeeRead,
    PayeeSpending,
    PayeeUpdate,
    SpendingByPayee,
)
from app.domains.payees.service import PayeeService

router = APIRouter(prefix="/payees", tags=["payees"])


def get_payee_repository(db: DbSession) -> PayeeRepository:
    return SqlPayeeRepository(db)


def get_payee_service(
    repo: Annotated[PayeeRepository, Depends(get_payee_repository)],
) -> PayeeService:
    return PayeeService(repo)


ServiceDep = Annotated[PayeeService, Depends(get_payee_service)]
RepoDep = Annotated[PayeeRepository, Depends(get_payee_repository)]


@router.get("", response_model=ApiResponse[list[PayeeRead]])
async def list_payees(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[PayeeRead]]:
    items = await service.list_payees(user.id)
    return ApiResponse(data=[PayeeRead.model_validate(p) for p in items])


@router.get("/new", response_model=ApiResponse[list[PayeeRead]])
async def list_new_payees(
    user: CurrentUser, service: ServiceDep
) -> ApiResponse[list[PayeeRead]]:
    """Кого раньше не было: забытая подписка или чужое списание."""
    rows = await service.new_payees(user.id, datetime.now(UTC))
    return ApiResponse(
        data=[PayeeRead.model_validate(p) for p, _ in rows],
        meta={"since": {str(p.id): seen.isoformat() for p, seen in rows}},
    )


@router.get("/spending", response_model=ApiResponse[SpendingByPayee])
async def spending_by_payee(
    user: CurrentUser,
    repo: RepoDep,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
) -> ApiResponse[SpendingByPayee]:
    """Кому ушли деньги за месяц. Категория говорит на что, этот — кому."""
    year, mon = (int(part) for part in month.split("-"))
    start, end = month_bounds_utc(
        datetime(year, mon, 1, tzinfo=UTC).date(), user.timezone
    )
    rows = await repo.spending_by_payee(user.id, start, end)
    items = [
        PayeeSpending(
            payee_id=row[0], name=row[1], amount_rub=row[2], operations=row[3]
        )
        for row in rows
    ]
    return ApiResponse(
        data=SpendingByPayee(
            month=month,
            items=items,
            total_rub=sum(
                (i.amount_rub for i in items), start=items[0].amount_rub * 0
            )
            if items
            else 0,
        )
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[PayeeRead],
)
async def create_payee(
    data: PayeeCreate, user: CurrentUser, service: ServiceDep, db: DbSession
) -> ApiResponse[PayeeRead]:
    payee = await service.create_payee(user.id, data)
    await db.commit()
    return ApiResponse(data=PayeeRead.model_validate(payee))


@router.patch("/{payee_id}", response_model=ApiResponse[PayeeRead])
async def update_payee(
    payee_id: uuid.UUID,
    data: PayeeUpdate,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[PayeeRead]:
    payee = await service.update_payee(payee_id, user.id, data)
    await db.commit()
    return ApiResponse(data=PayeeRead.model_validate(payee))


@router.post(
    "/{payee_id}/merge/{target_id}", response_model=ApiResponse[dict[str, int]]
)
async def merge_payees(
    payee_id: uuid.UUID,
    target_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> ApiResponse[dict[str, int]]:
    """Слить получателя в другого: один магазин под двумя именами."""
    moved = await service.merge_payees(payee_id, target_id, user.id)
    await db.commit()
    return ApiResponse(data={"moved": moved})


@router.delete("/{payee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee(
    payee_id: uuid.UUID,
    user: CurrentUser,
    service: ServiceDep,
    db: DbSession,
) -> None:
    await service.delete_payee(payee_id, user.id)
    await db.commit()
