"""Summary, ledger, provenance, verify (contract section 7). STUB: fixtures."""
from datetime import date

from fastapi import APIRouter, Query, Request

from .. import errors
from ..schemas import Classification, EntryType
from ..stubs import fixture, require_merchant

router = APIRouter(tags=["ledger"])


@router.get("/merchants/{merchant_id}/summary")
def summary(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    include_sources: bool = False,
):
    require_merchant(merchant_id)
    out = fixture("summary_M001_after_confirm")
    if not include_sources:
        out["sources"] = None
    return out


@router.get("/merchants/{merchant_id}/ledger")
def ledger(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    entry_type: EntryType | None = None,
    classification: Classification | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    require_merchant(merchant_id)
    out = fixture("ledger_M001_2026-11-15")
    items = out["items"]
    if entry_type:
        items = [i for i in items if i["entry_type"] == entry_type]
    if classification:
        items = [i for i in items if i["classification"] == classification]
    out["items"] = items[offset : offset + limit]
    out["count"] = len(out["items"])
    return out


@router.get("/ledger/{ledger_entry_id}")
def ledger_entry(ledger_entry_id: str):
    detail = fixture("ledger_entry_detail")
    if detail["ledger_entry_id"] != ledger_entry_id:
        raise errors.not_found(f"Unknown ledger entry {ledger_entry_id}", ledger_entry_id=ledger_entry_id)
    return detail


@router.get("/merchants/{merchant_id}/ledger/verify")
def verify(merchant_id: str, request: Request):
    require_merchant(merchant_id)
    return fixture("ledger_verify_tampered" if request.app.state.demo.tampered else "ledger_verify_valid")
