"""Summary, ledger, provenance, verify (contract section 7). All real."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query

from .. import clock, errors, money, periods, repo
from ..deps import get_conn
from ..finance.summary import ATTRIBUTION_NOTE, SCOPE_NOTE, compute
from ..ledger import writer as ledger
from ..ledger.hashing import verify_chain
from ..schemas import Classification, EntryType
from ..services.payments import payment_detail

router = APIRouter(tags=["ledger"])



@router.get("/merchants/{merchant_id}/summary")
def summary(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    include_sources: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
):
    repo.require_merchant(conn, merchant_id)
    start, end = periods.resolve(start_date, end_date)
    b = compute(conn, merchant_id, start, end)
    return {
        "merchant_id": merchant_id,
        "period": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "total_collections": money.amount(b.total_collections),
        "business_sales": money.amount(b.business_sales),
        "family_transfers": money.amount(b.family_transfers),
        "pending": {**money.amount(b.pending), "count": b.pending_count},
        "refunds": money.amount(b.refunds),
        "reversals": money.amount(b.reversals),
        "expenses": money.amount(b.expenses),
        "profit": {**money.amount(b.profit), "label": "Recorded profit"},
        "scope_note": SCOPE_NOTE,
        "attribution_note": ATTRIBUTION_NOTE,
        "as_of": clock.iso(clock.effective_now(ledger.last_created_at(conn, merchant_id))),
        "reconciliation_ok": b.reconciliation_ok,
        "sources": b.sources if include_sources else None,
    }


@router.get("/merchants/{merchant_id}/ledger")
def ledger_list(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    entry_type: EntryType | None = None,
    classification: Classification | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    repo.require_merchant(conn, merchant_id)
    start, end = periods.resolve(start_date, end_date)
    sql = "SELECT * FROM ledger_entries WHERE merchant_id = ? AND substr(effective_at, 1, 10) BETWEEN ? AND ?"
    args: list = [merchant_id, start.isoformat(), end.isoformat()]
    if entry_type:
        sql += " AND entry_type = ?"
        args.append(entry_type)
    if classification:
        sql += " AND classification = ?"
        args.append(classification)
    total = conn.execute(sql.replace("SELECT *", "SELECT COUNT(*)", 1), args).fetchone()[0]
    sql += " ORDER BY seq LIMIT ? OFFSET ?"
    items = [ledger.to_api(r) for r in conn.execute(sql, [*args, limit, offset])]
    return {"merchant_id": merchant_id, "count": total, "items": items}


def _source(conn: sqlite3.Connection, row) -> dict | None:
    if row["source_type"] in ("PAYMENT", "REVERSAL"):
        return payment_detail(conn, row["source_id"])
    if row["source_type"] == "EXPENSE":
        e = conn.execute("SELECT * FROM expenses WHERE expense_id = ?", (row["source_id"],)).fetchone()
        voided = conn.execute("SELECT 1 FROM expense_voids WHERE expense_id = ?", (row["source_id"],)).fetchone()
        return {
            "expense_id": e["expense_id"], "timestamp": e["timestamp"], "amount_paise": e["amount_paise"],
            "amount_display": money.display(e["amount_paise"]), "category": e["category"],
            "description": e["description"], "input_source": e["input_source"], "voided": voided is not None,
        }
    if row["source_type"] == "REFUND":
        r = conn.execute("SELECT * FROM refunds WHERE refund_id = ?", (row["source_id"],)).fetchone()
        return {
            "refund_id": r["refund_id"], "transaction_id": r["transaction_id"], "amount_paise": r["amount_paise"],
            "amount_display": money.display(r["amount_paise"]), "timestamp": r["timestamp"], "reason": r["reason"],
        }
    return None


@router.get("/ledger/{ledger_entry_id}")
def ledger_entry(ledger_entry_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = conn.execute("SELECT * FROM ledger_entries WHERE ledger_entry_id = ?", (ledger_entry_id,)).fetchone()
    if row is None:
        raise errors.not_found(f"Unknown ledger entry {ledger_entry_id}", ledger_entry_id=ledger_entry_id)
    return {**ledger.to_api(row), "source": _source(conn, row)}


VERIFY_MESSAGES = {
    "hash_mismatch": "Entry {id} was changed after it was written (hash_mismatch).",
    "prev_hash_mismatch": "Entry {id} does not link to the entry before it (prev_hash_mismatch): "
                          "an entry was inserted, deleted or reordered.",
}


@router.get("/merchants/{merchant_id}/ledger/verify")
def verify(merchant_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    repo.require_merchant(conn, merchant_id)
    rows = conn.execute("SELECT * FROM ledger_entries WHERE merchant_id = ? ORDER BY seq", (merchant_id,)).fetchall()
    result = verify_chain(rows)
    if result.status == "VALID":
        message = f"All {result.entries_checked} entries verified. No changes detected."
    else:
        message = VERIFY_MESSAGES[result.problem].format(id=result.first_invalid_entry_id)
    return {"merchant_id": merchant_id, "status": result.status, "entries_checked": result.entries_checked,
            "first_invalid_entry_id": result.first_invalid_entry_id, "message": message}
