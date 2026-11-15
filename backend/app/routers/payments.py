"""Payments, questions, confirmation, preview (contract sections 3-4).

REAL: POST /payments, GET /payments/{txn}, payments list, GET questions, POST confirm.
STUB (fixtures): refund, reversal, classify preview (services exist; routes switch after the classifier).
"""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from .. import periods
from ..deps import get_conn
from ..schemas import Classification, ConfirmIn, Language, PaymentIn, PreviewIn, QuestionStatus, RefundIn, ReversalIn
from ..services import payments as svc
from ..stubs import fixture, require_merchant_422

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
def refund(transaction_id: str, body: RefundIn):
    return fixture("refund")  # STUB


@router.post("/payments/{transaction_id}/reversal", status_code=201)
def reversal(transaction_id: str, body: ReversalIn):
    return fixture("reversal")  # STUB


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
def classify_preview(body: PreviewIn):
    require_merchant_422(body.merchant_id)  # STUB
    return fixture("classify_preview_remembered")
