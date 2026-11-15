"""Payments, questions, confirmation, preview (contract sections 3-4).

All real: POST /payments, GET /payments/{txn}, payments list, refund, reversal, questions, confirm, preview.
"""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from .. import clock, periods, repo
from ..classifier.decide import decide
from ..deps import get_conn
from ..schemas import Classification, ConfirmIn, Language, PaymentIn, PreviewIn, QuestionStatus, RefundIn, ReversalIn
from ..services import payments as svc

router = APIRouter(tags=["payments"])


@router.post("/payments", status_code=201)
def create_payment(body: PaymentIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.create_payment(conn, body)
    response.status_code = status
    return out


@router.get("/payments/{transaction_id}")
def get_payment(transaction_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.payment_detail(conn, transaction_id)


@router.get("/merchants/{merchant_id}/payments")
def list_payments(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    classification: Classification | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    start, end = periods.resolve(start_date, end_date)
    return svc.list_payments(conn, merchant_id, start, end, classification, limit, offset)


@router.post("/payments/{transaction_id}/refund", status_code=201)
def refund(transaction_id: str, body: RefundIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.refund(conn, transaction_id, body)
    response.status_code = status
    return out


@router.post("/payments/{transaction_id}/reversal", status_code=201)
def reversal(transaction_id: str, body: ReversalIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.reverse(conn, transaction_id, body)
    response.status_code = status
    return out


@router.get("/merchants/{merchant_id}/questions")
def list_questions(
    merchant_id: str,
    status: QuestionStatus = "OPEN",
    date: date | None = None,
    language: Language | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return svc.list_questions(conn, merchant_id, status=status, date=date.isoformat() if date else None,
                              language=language)


@router.post("/payments/{transaction_id}/confirm", status_code=201)
def confirm(transaction_id: str, body: ConfirmIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.confirm(conn, transaction_id, body)
    response.status_code = status
    return out


@router.post("/classify/preview")
def classify_preview(body: PreviewIn, conn: sqlite3.Connection = Depends(get_conn)):
    """The full decision procedure for a hypothetical payment. Writes nothing."""
    repo.require_merchant_in_body(conn, body.merchant_id)
    d = decide(conn, merchant_id=body.merchant_id, payer_id=body.payer_id, payer_vpa_kind=_payer_kind(conn, body.payer_id),
               amount_paise=body.amount_paise, payment_type=body.payment_type,
               timestamp=clock.iso(clock.parse(body.timestamp)))
    return {"suggested_classification": d.suggested, "confidence": d.confidence, "confidence_kind": d.confidence_kind,
            "action": d.action, "classification_source": d.source, "reasons": d.reasons, "written": False}


def _payer_kind(conn: sqlite3.Connection, payer_id: str) -> str:
    """The preview request has no payer_vpa_kind: use the known payer's, else PERSONAL (as a new payer)."""
    row = conn.execute("SELECT payer_vpa_kind FROM payers WHERE payer_id = ?", (payer_id,)).fetchone()
    return row["payer_vpa_kind"] if row else "PERSONAL"
