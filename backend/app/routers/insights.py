"""Learning, evaluation, tax summary, notices, passport (contract sections 8-10).

REAL: learning, evaluation, tax summary, passport, notice evidence (Asitha).
notice analyse: notice/analyse.py, the agreed fallback for the committed sample (Asitha); the real reader is not
written yet.
"""
import sqlite3
import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from .. import errors
from ..config import REPO_ROOT
from ..deps import get_conn
from ..finance import threshold
from ..notice.analyse import analyse
from ..notice.evidence import evidence
from ..services import insights as svc


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


@router.get("/merchants/{merchant_id}/threshold-watch")
def threshold_watch(merchant_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """This financial year's business sales against the ₹40 lakh GST threshold for goods (read-only)."""
    return threshold.watch(conn, merchant_id)


@router.get("/merchants/{merchant_id}/tax-summary")
def tax_summary(merchant_id: str, start_date: date | None = None, end_date: date | None = None,
                conn: sqlite3.Connection = Depends(get_conn)):
    return svc.tax_summary(conn, merchant_id, start_date, end_date)


@router.post("/notices/analyse", status_code=201)
async def analyse_notice(
    merchant_id: str = Form(...),
    file: UploadFile = File(...),
    demo_key: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Calls notice.analyse.analyse (currently the agreed fallback for the committed sample)."""
    data = await file.read()
    if not data:
        raise errors.validation_error("Empty file", field="file")
    return analyse(conn, merchant_id=merchant_id, file_bytes=data, demo_key=demo_key)


@router.get("/merchants/{merchant_id}/notices/{notice_id}/evidence")
def notice_evidence(merchant_id: str, notice_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    """REAL (Asitha): DATA 9 from the stored notice (saved by analyse() via notice.store.save_notice)."""
    return evidence(conn, merchant_id=merchant_id, notice_id=notice_id)


@router.get("/merchants/{merchant_id}/passport")
def passport(merchant_id: str, months: int = Query(3, ge=1, le=3), conn: sqlite3.Connection = Depends(get_conn)):
    return svc.passport(conn, merchant_id, months)
