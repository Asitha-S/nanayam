"""Notice evidence (DATA_AND_LOGIC 9; contract section 9 GET /merchants/{id}/notices/{nid}/evidence). Owner: Asitha.

Every ledger figure comes from finance.summary.compute for the notice period and is tagged DERIVED_FROM_LEDGER;
the amount questioned is the notice's own value, tagged EXTRACTED_FROM_NOTICE. No figure is invented: where the
ledger has no data for part of the period the bucket stays 0 and a warning says so.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from .. import clock, errors, money, repo
from ..finance.summary import compute
from ..services.insights import GST, verify_status
from .store import load_notice

FIXED_WARNINGS = [
    "GST treatment is based on the merchant's declared category, not on individual sales.",
    "Family transfer labels are the merchant's own confirmations.",
    "Cash sales and payments through other apps are not in this ledger.",
]
MAX_FAMILY_EXAMPLES = 5


def _field(fields: dict, name: str):
    f = fields.get(name) or {}
    if f.get("origin") == "NOT_FOUND" or f.get("value") is None:
        return None
    return f["value"]


def _ledger(amount: int, count: int | None = None) -> dict:
    out = {**money.amount(amount), "origin": "DERIVED_FROM_LEDGER"}
    if count is not None:
        out["entry_count"] = count
    return out


def family_examples(conn: sqlite3.Connection, merchant_id: str, start: date, end: date) -> list[dict]:
    """Up to 5 FAMILY payments in the period, largest first, labelled by the merchant (configured or confirmed)."""
    rows = conn.execute(
        """
        SELECT p.transaction_id, p.timestamp, py.payer_name, p.amount_paise, le.classification_source
        FROM payments p JOIN payers py ON py.payer_id = p.payer_id
        JOIN ledger_entries le ON le.ledger_entry_id = (
            SELECT l2.ledger_entry_id FROM ledger_entries l2
            WHERE l2.source_type = 'PAYMENT' AND l2.source_id = p.transaction_id
              AND l2.entry_type IN ('PAYMENT_IN', 'RECLASSIFICATION') ORDER BY l2.seq DESC LIMIT 1)
        WHERE p.merchant_id = ? AND substr(p.timestamp, 1, 10) BETWEEN ? AND ? AND le.classification = 'FAMILY'
          AND le.classification_source IN ('MERCHANT_CONFIG', 'MERCHANT_CONFIRMED')
          AND NOT EXISTS (SELECT 1 FROM reversals v WHERE v.transaction_id = p.transaction_id)
        ORDER BY p.amount_paise DESC, p.timestamp LIMIT ?
        """, (merchant_id, start.isoformat(), end.isoformat(), MAX_FAMILY_EXAMPLES)).fetchall()
    return [{"transaction_id": r[0], "date": r[1][:10], "payer_name": r[2], "amount_display": money.display(r[3]),
             "confirmed_by": r[4]} for r in rows]


def evidence(conn: sqlite3.Connection, *, merchant_id: str, notice_id: str) -> dict:
    merchant = repo.require_merchant(conn, merchant_id)
    notice = load_notice(conn, merchant_id, notice_id)
    fields = notice["fields"]
    start_v, end_v = _field(fields, "period_start"), _field(fields, "period_end")
    if start_v is None or end_v is None:
        raise errors.validation_error("Could not read the notice period. Evidence not generated.", field="period")
    start, end = date.fromisoformat(start_v), date.fromisoformat(end_v)
    if end < start:
        raise errors.validation_error("Notice period ends before it starts. Evidence not generated.", field="period")

    b = compute(conn, merchant_id, start, end)
    status = verify_status(conn, merchant_id)
    questioned = _field(fields, "amount_questioned_paise")
    warnings = list(FIXED_WARNINGS)
    if b.pending_count:
        warnings.append(f"{b.pending_count} payments in this period are still unconfirmed.")
    if status != "VALID":
        warnings.append("Ledger integrity check failed.")
    first, last = conn.execute("SELECT MIN(substr(timestamp, 1, 10)), MAX(substr(timestamp, 1, 10)) FROM payments"
                               " WHERE merchant_id = ?", (merchant_id,)).fetchone()
    if first is None or first > start.isoformat() or end > clock.today():
        warnings.append("The ledger has no records for part of this period; those days count as 0.")

    if questioned is None:
        difference = {"amount_paise": None, "amount_display": None,
                      "explanation": "The notice amount could not be read, so no difference is shown."}
        warnings.append("Amount questioned was not found on the notice.")
    else:
        diff = int(questioned) - b.total_collections
        if diff == 0:
            explanation = ("The notice amount matches total UPI collections in the ledger. The breakdown below shows "
                           "how much of it was business sales.")
        else:
            explanation = (f"The notice amount differs from ledger collections by {money.display(abs(diff))}. Possible "
                           "reasons: payments to other accounts, or cash. A CA must check.")
        difference = {**money.amount(diff), "explanation": explanation}

    return {
        "notice_id": notice_id,
        "period": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "amount_questioned": ({**money.amount(int(questioned)), "origin": "EXTRACTED_FROM_NOTICE"} if questioned is not None
                              else {"amount_paise": None, "amount_display": None, "origin": "NOT_FOUND"}),
        "ledger_view": {
            "total_collections": _ledger(b.total_collections),
            "business_sales": _ledger(b.business_sales, b.business_sales_count),
            "family_transfers": _ledger(b.family_transfers, b.family_transfers_count),
            "refunds_and_reversals": _ledger(b.refunds + b.reversals),
            "unresolved": _ledger(b.pending, b.pending_count),
            "expenses_recorded": _ledger(b.expenses, b.expenses_count),
        },
        "difference_vs_notice": difference,
        "gst_treatment": GST[merchant["business_category"]][0],
        "family_transfer_examples": family_examples(conn, merchant_id, start, end),
        "ca_review_warnings": warnings,
        "ledger_verify_status": status,
    }
