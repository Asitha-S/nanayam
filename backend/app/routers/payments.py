"""Payments, questions, confirmation, preview (contract sections 3-4). STUB: fixtures."""
from datetime import date

from fastapi import APIRouter, Query

from .. import errors
from ..schemas import Classification, ConfirmIn, Language, PaymentIn, PreviewIn, QuestionStatus, RefundIn, ReversalIn
from ..stubs import fixture, require_merchant, require_merchant_422

router = APIRouter(tags=["payments"])

ASK_TXN = "TXN-M001-20261115-015"


@router.post("/payments", status_code=201)
def create_payment(body: PaymentIn):
    require_merchant_422(body.merchant_id)
    return fixture("payments_post_015_ask" if body.transaction_id == ASK_TXN else "payments_post_012_auto")


@router.get("/payments/{transaction_id}")
def get_payment(transaction_id: str):
    if transaction_id != ASK_TXN:
        raise errors.not_found(f"Unknown transaction {transaction_id}", transaction_id=transaction_id)
    return fixture("payment_get_015")


@router.get("/merchants/{merchant_id}/payments")
def list_payments(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    classification: Classification | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    require_merchant(merchant_id)
    out = fixture("payments_list_M001_2026-11-15")
    if classification:
        out["items"] = [i for i in out["items"] if i["current_classification"] == classification]
    out["items"] = out["items"][offset : offset + limit]
    out["count"] = len(out["items"])
    return out


@router.post("/payments/{transaction_id}/refund", status_code=201)
def refund(transaction_id: str, body: RefundIn):
    return fixture("refund")


@router.post("/payments/{transaction_id}/reversal", status_code=201)
def reversal(transaction_id: str, body: ReversalIn):
    return fixture("reversal")


@router.get("/merchants/{merchant_id}/questions")
def list_questions(
    merchant_id: str,
    status: QuestionStatus = "OPEN",
    date: date | None = None,
    language: Language | None = None,
):
    require_merchant(merchant_id)
    if status != "OPEN":
        return {"merchant_id": merchant_id, "items": []}
    return fixture("questions_M001_open_2026-11-15" if date is not None else "questions_M001_open_all")


@router.post("/payments/{transaction_id}/confirm", status_code=201)
def confirm(transaction_id: str, body: ConfirmIn):
    require_merchant_422(body.merchant_id)
    out = fixture("confirm_015")
    if body.question_id is not None and (body.question_id != out["question_id"] or transaction_id != ASK_TXN):
        raise errors.invalid_state(
            f"question {body.question_id} does not belong to transaction {transaction_id}",
            reason="QUESTION_MISMATCH",
            question_id=body.question_id,
        )
    return out


@router.post("/classify/preview")
def classify_preview(body: PreviewIn):
    require_merchant_422(body.merchant_id)
    return fixture("classify_preview_remembered")
