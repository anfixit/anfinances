"""HTTP-роуты выгрузки: /export/*.

Эндпоинты отдают файл (Content-Disposition: attachment), а не
конверт ApiResponse — ожидаемое исключение из §24 для скачивания.
Read-only, commit не нужен.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.dependencies import CurrentUser, DbSession
from app.domains.export.repository import SqlExportRepository
from app.domains.export.service import ExportService

router = APIRouter(prefix="/export", tags=["export"])

_CSV_MEDIA = "text/csv; charset=utf-8"
_XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

DateFrom = Annotated[datetime | None, Query(alias="from")]
DateTo = Annotated[datetime | None, Query(alias="to")]


def get_export_service(db: DbSession) -> ExportService:
    return ExportService(SqlExportRepository(db))


ServiceDep = Annotated[ExportService, Depends(get_export_service)]


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("/transactions.csv")
async def export_transactions_csv(
    user: CurrentUser,
    service: ServiceDep,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Response:
    content = await service.transactions_csv(user.id, date_from, date_to)
    return Response(
        content=content,
        media_type=_CSV_MEDIA,
        headers=_attachment("transactions.csv"),
    )


@router.get("/transactions.xlsx")
async def export_transactions_xlsx(
    user: CurrentUser,
    service: ServiceDep,
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> Response:
    content = await service.transactions_xlsx(user.id, date_from, date_to)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers=_attachment("transactions.xlsx"),
    )


@router.get("/all.json")
async def export_all_json(user: CurrentUser, service: ServiceDep) -> Response:
    content = await service.build_backup_json(user.id)
    return Response(
        content=content,
        media_type="application/json",
        headers=_attachment("anfinances-backup.json"),
    )
