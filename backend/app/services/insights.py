"""Merchants (contract 2), learning (8), tax summary (9), credit passport (10). Amounts only via finance.summary."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .. import clock, db, errors, money, repo
from ..feedback.memory import payer_counts
from ..finance.summary import compute
from ..ledger.hashing import verify_chain


# --- merchants -----------------------------------------------------------------------------
def merchant_summary(row) -> dict:
    return {k: row[k] for k in ("merchant_id", "display_name", "owner_name", "business_category", "preferred_language")}


def list_merchants(conn: sqlite3.Connection) -> dict:
    return {"merchants": [merchant_summary(r) for r in conn.execute("SELECT * FROM merchants ORDER BY merchant_id")]}


def merchant_detail(conn: sqlite3.Connection, merchant_id: str) -> dict:
    m = repo.require_merchant(conn, merchant_id)
    family = conn.execute(
        "SELECT f.payer_id, p.payer_name, f.relation_label FROM merchant_family_payers f"
        " JOIN payers p USING (payer_id) WHERE f.merchant_id = ? ORDER BY f.added_at, f.payer_id", (merchant_id,))
    return {**merchant_summary(m), "city": m["city"], "created_at": m["created_at"],
            "family_payers": [dict(r) for r in family]}


def update_merchant(conn: sqlite3.Connection, merchant_id: str, req) -> dict:
    """Partial update. family_payer_ids replaces the configured list; affects future payments only."""
    with db.write_tx(conn):
        repo.require_merchant(conn, merchant_id)
        if req.preferred_language is not None:
            conn.execute("UPDATE merchants SET preferred_language = ? WHERE merchant_id = ?",
                         (req.preferred_language, merchant_id))
        if req.business_category is not None:
            conn.execute("UPDATE merchants SET business_category = ? WHERE merchant_id = ?",
                         (req.business_category, merchant_id))
        if req.family_payer_ids is not None:
            wanted = list(dict.fromkeys(req.family_payer_ids))
            unknown = [p for p in wanted if not conn.execute("SELECT 1 FROM payers WHERE payer_id = ?", (p,)).fetchone()]
            if unknown:
                raise errors.validation_error(f"Unknown payer IDs: {', '.join(unknown)}", field="family_payer_ids",
                                              unknown=unknown)
            current = {r[0] for r in conn.execute("SELECT payer_id FROM merchant_family_payers WHERE merchant_id = ?",
                                                  (merchant_id,))}
            for pid in current - set(wanted):
                conn.execute("DELETE FROM merchant_family_payers WHERE merchant_id = ? AND payer_id = ?", (merchant_id, pid))
            now = clock.iso(clock.now())
            for pid in wanted:
                if pid not in current:
                    repo.add_family_payer(conn, merchant_id, pid, None, now, "SETUP")
    return merchant_detail(conn, merchant_id)


# --- learning (merchant activity; model metrics come from /evaluation) -----------------------
def _questions_between(conn, merchant_id: str, start: date, end: date) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM questions q JOIN payments p USING (transaction_id)"
        " WHERE q.merchant_id = ? AND substr(p.timestamp, 1, 10) BETWEEN ? AND ?",
        (merchant_id, start.isoformat(), end.isoformat())).fetchone()[0]


def learning(conn: sqlite3.Connection, merchant_id: str) -> dict:
    m = repo.require_merchant(conn, merchant_id)
    today = clock.today()
    first_day = clock.parse(m["created_at"]).date()
    one = lambda sql, *args: conn.execute(sql, (merchant_id, *args)).fetchone()[0]  # noqa: E731
    configured = {r["payer_id"]: r for r in conn.execute(
        "SELECT f.payer_id, p.payer_name, f.relation_label, f.added_via FROM merchant_family_payers f"
        " JOIN payers p USING (payer_id) WHERE f.merchant_id = ?", (merchant_id,))}
    with_feedback = {r[0]: r[1] for r in conn.execute(
        "SELECT DISTINCT f.payer_id, p.payer_name FROM feedback f JOIN payers p USING (payer_id) WHERE f.merchant_id = ?",
        (merchant_id,))}
    payers = []
    for pid in sorted(set(configured) | set(with_feedback)):
        n_family, n_sale = payer_counts(conn, merchant_id, pid)
        n = n_family + n_sale
        if pid in configured:
            kind = "INSTRUCTION"  # "always family (your instruction)"
        elif n >= 3 and min(n_family, n_sale) / n >= 0.25:
            kind = "MIXED"  # "mixed payer, always asked" (rule 5a)
        else:
            kind = "MEMORY"  # answers nudge the model
        payers.append({"payer_id": pid, "payer_name": configured[pid]["payer_name"] if pid in configured else with_feedback[pid],
                       "kind": kind, "relation_label": configured[pid]["relation_label"] if pid in configured else None,
                       "confirmed_family": n_family, "confirmed_sale": n_sale})
    recent = conn.execute(
        "SELECT f.feedback_id, p.payer_name, f.confirmed_category, f.created_at FROM feedback f"
        " JOIN payers p USING (payer_id) WHERE f.merchant_id = ? ORDER BY f.feedback_id DESC LIMIT 5", (merchant_id,))
    return {
        "merchant_id": merchant_id,
        "corrections_total": one("SELECT COUNT(*) FROM feedback WHERE merchant_id = ?"),
        "known_payers": one("SELECT COUNT(DISTINCT payer_id) FROM payments WHERE merchant_id = ?"),
        "payers_with_memory": len(with_feedback),
        "family_payers_configured": len(configured),
        "questions_asked": {
            "today": _questions_between(conn, merchant_id, today, today),
            "last_7_days": _questions_between(conn, merchant_id, today - timedelta(days=6), today),
            "first_7_days": _questions_between(conn, merchant_id, first_day, first_day + timedelta(days=6)),
        },
        "auto_classified_today": one(
            "SELECT COUNT(*) FROM payments p JOIN predictions pr USING (transaction_id) WHERE p.merchant_id = ?"
            " AND substr(p.timestamp, 1, 10) = ? AND pr.action = 'AUTO_CLASSIFY'", today.isoformat()),
        "recent_feedback": [{"feedback_id": r[0], "payer_name": r[1], "confirmed_category": r[2], "at": r[3]}
                            for r in recent],
        "payers": payers,
    }


# --- tax summary (DATA 8) -------------------------------------------------------------------
GST = {
    "VEGETABLES": ("EXEMPT_LIKELY", "Merchant configured category VEGETABLES (fresh vegetables are generally "
                                    "GST-exempt). Not inferred from payments."),
    "FRUITS": ("EXEMPT_LIKELY", "Merchant configured category FRUITS (fresh fruits are generally GST-exempt). "
                                "Not inferred from payments."),
    "FLOWERS": ("EXEMPT_LIKELY", "Merchant configured category FLOWERS (fresh flowers are generally GST-exempt). "
                                 "Not inferred from payments."),
    "TEA_STALL": ("TAXABLE_LIKELY", "Merchant configured category TEA_STALL (prepared food and drinks are generally "
                                    "taxable). Not inferred from payments."),
    "MIXED_KIRANA": ("UNKNOWN", "Mixed goods. The split between exempt and taxable sales cannot be known from UPI "
                                "payments."),
}
TAX_PERIOD_START = date(2026, 8, 1)


def tax_summary(conn: sqlite3.Connection, merchant_id: str, start: date | None, end: date | None) -> dict:
    m = repo.require_merchant(conn, merchant_id)
    end = end or clock.today()
    start = start or TAX_PERIOD_START
    if end < start:
        raise errors.validation_error("end_date is before start_date", field="end_date")
    treatment, basis = GST[m["business_category"]]
    b = compute(conn, merchant_id, start, end)
    flags = (["MIXED_CATEGORY_SPLIT_UNKNOWN"] if treatment == "UNKNOWN" else []) + ["CA_REVIEW_REQUIRED"]
    return {
        "merchant_id": merchant_id,
        "period": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "business_category": m["business_category"],
        "gst_treatment": treatment,
        "gst_treatment_basis": basis,
        "ca_review_required": True,
        "total_collections": money.amount(b.total_collections),
        "business_sales": money.amount(b.business_sales),
        "family_transfers": money.amount(b.family_transfers),
        "pending": {**money.amount(b.pending), "count": b.pending_count},
        "expenses_recorded": {**money.amount(b.expenses), "count": b.expenses_count},
        "flags": flags,
    }


# --- credit passport (DATA 10; show only) -----------------------------------------------------
PASSPORT_LABEL = "Recorded business income summary. Not verified income. Not a credit decision."
CONSENT_NOTE = "Shared only with the merchant's consent."


def _complete_months_before(day: date, n: int) -> list[tuple[date, date]]:
    months = []
    first = day.replace(day=1)
    for _ in range(n):
        end = first - timedelta(days=1)
        first = end.replace(day=1)
        months.append((first, end))
    return list(reversed(months))


def verify_status(conn: sqlite3.Connection, merchant_id: str) -> str:
    rows = conn.execute("SELECT * FROM ledger_entries WHERE merchant_id = ? ORDER BY seq", (merchant_id,)).fetchall()
    return verify_chain(rows).status


def passport(conn: sqlite3.Connection, merchant_id: str, months: int) -> dict:
    repo.require_merchant(conn, merchant_id)
    out, raw_total, income_total = [], 0, 0
    for start, end in _complete_months_before(clock.today(), months):
        b = compute(conn, merchant_id, start, end)
        values = {"raw_collections": b.total_collections, "family_transfers": b.family_transfers,
                  "refunds_reversals": b.refunds + b.reversals, "business_sales": b.business_sales,
                  "expenses": b.expenses, "recorded_income": b.business_sales}
        month = {"month": start.strftime("%Y-%m")}
        for k, v in values.items():
            month[f"{k}_display"] = money.display(v)
            month[f"{k}_paise"] = v
        month["unresolved_count"] = b.pending_count
        out.append(month)
        raw_total += b.total_collections
        income_total += b.business_sales
    return {
        "merchant_id": merchant_id,
        "months": out,
        "totals": {"raw_collections": money.amount(raw_total), "recorded_business_income": money.amount(income_total)},
        "share_of_collections_that_were_business_sales": round(income_total / raw_total, 3) if raw_total else 0.0,
        "ledger_verify_status": verify_status(conn, merchant_id),
        "label": PASSPORT_LABEL,
        "consent_note": CONSENT_NOTE,
    }
