"""Learning, evaluation, tax summary, notices, passport (contract sections 8-10).

REAL: learning, evaluation, tax summary, passport. STUB (fixtures): notices (Charulatha's backend/app/notice/).
"""
import sqlite3
import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from .. import errors
from ..config import REPO_ROOT
from ..deps import get_conn
from ..services import insights as svc
from ..stubs import fixture, require_merchant, require_merchant_422

router = APIRouter(tags=["insights"])


@router.get("/merchants/{merchant_id}/learning")
def learning(merchant_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.learning(conn, merchant_id)


@router.get("/evaluation")
def evaluation():
    """REAL: the latest run file written by python -m ml.evaluate (never hand-edited)."""
    path = REPO_ROOT / "data" / "eval" / "latest.json"
    if not path.exists():
        raise errors.not_found("No evaluation run yet. Run python -m ml.evaluate.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/merchants/{merchant_id}/tax-summary")
def tax_summary(merchant_id: str, start_date: date | None = None, end_date: date | None = None,
                conn: sqlite3.Connection = Depends(get_conn)):
    return svc.tax_summary(conn, merchant_id, start_date, end_date)


@router.post("/notices/analyse", status_code=201)
async def analyse_notice(
    merchant_id: str = Form(...),
    file: UploadFile = File(...),
    demo_key: str | None = Form(None),
):
    require_merchant_422(merchant_id)
    if not await file.read():
        raise errors.validation_error("Empty file", field="file")
    return fixture("notice_analyse")


@router.get("/merchants/{merchant_id}/notices/{notice_id}/evidence")
def notice_evidence(merchant_id: str, notice_id: str):
    require_merchant(merchant_id)
    out = fixture("notice_evidence")
    if notice_id != out["notice_id"]:
        raise errors.not_found(f"Unknown notice {notice_id}", notice_id=notice_id)
    return out


@router.get("/merchants/{merchant_id}/passport")
def passport(merchant_id: str, months: int = Query(3, ge=1, le=3), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.passport(conn, merchant_id, months)
