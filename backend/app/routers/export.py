"""CA export (contract section 11). REAL: backend/app/export/builders.py (Asitha)."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Response

from .. import clock, errors
from ..deps import get_conn
from ..export.builders import csv_export, filename, pdf_export

router = APIRouter(tags=["export"])
TAX_YEAR_START = date(2026, 8, 1)  # default period, as the tax summary


def _period(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or clock.today()
    start = start_date or TAX_YEAR_START
    if end < start:
        raise errors.validation_error("end_date is before start_date", field="end_date")
    return start, end


@router.get("/merchants/{merchant_id}/export/csv")
def export_csv(merchant_id: str, start_date: date | None = None, end_date: date | None = None,
               conn: sqlite3.Connection = Depends(get_conn)):
    start, end = _period(start_date, end_date)
    body = csv_export(conn, merchant_id=merchant_id, start=start, end=end)
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename(merchant_id, start, end, "csv")}"'})


@router.get("/merchants/{merchant_id}/export/pdf")
def export_pdf(merchant_id: str, start_date: date | None = None, end_date: date | None = None,
               conn: sqlite3.Connection = Depends(get_conn)):
    start, end = _period(start_date, end_date)
    body = pdf_export(conn, merchant_id=merchant_id, start=start, end=end)
    return Response(content=body, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename(merchant_id, start, end, "pdf")}"'})
