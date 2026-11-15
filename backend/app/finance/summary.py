"""Financial buckets for a period (DATA_AND_LOGIC 7.3). The one place money totals are computed.

Used by /summary and /voice/answer, and by notice evidence, tax summary, passport and export.
Payments are attributed to the IST date of the original payment; refunds and reversals attach to
their payment (state as of now); expenses to the expense timestamp.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

PAYMENTS_SQL = """
SELECT p.transaction_id, p.amount_paise AS g,
       (SELECT COALESCE(SUM(r.amount_paise), 0) FROM refunds r WHERE r.transaction_id = p.transaction_id) AS r,
       EXISTS (SELECT 1 FROM reversals v WHERE v.transaction_id = p.transaction_id) AS reversed,
       le.ledger_entry_id AS class_entry_id, le.classification
FROM payments p
JOIN ledger_entries le ON le.ledger_entry_id = (
    SELECT l2.ledger_entry_id FROM ledger_entries l2
    WHERE l2.source_type = 'PAYMENT' AND l2.source_id = p.transaction_id
      AND l2.entry_type IN ('PAYMENT_IN', 'RECLASSIFICATION')
    ORDER BY l2.seq DESC LIMIT 1)
WHERE p.merchant_id = ? AND substr(p.timestamp, 1, 10) BETWEEN ? AND ?
ORDER BY p.timestamp, p.transaction_id
"""

REFUND_ENTRIES_SQL = """
SELECT le.ledger_entry_id FROM refunds r
JOIN ledger_entries le ON le.source_type = 'REFUND' AND le.source_id = r.refund_id AND le.entry_type = 'REFUND_OUT'
WHERE r.transaction_id = ? ORDER BY le.seq
"""

EXPENSES_SQL = """
SELECT e.expense_id, e.amount_paise, le.ledger_entry_id FROM expenses e
JOIN ledger_entries le ON le.source_type = 'EXPENSE' AND le.source_id = e.expense_id AND le.entry_type = 'EXPENSE'
WHERE e.merchant_id = ? AND substr(e.timestamp, 1, 10) BETWEEN ? AND ?
  AND NOT EXISTS (SELECT 1 FROM expense_voids v WHERE v.expense_id = e.expense_id)
ORDER BY e.timestamp, e.expense_id
"""


@dataclass
class Buckets:
    total_collections: int = 0
    business_sales: int = 0
    family_transfers: int = 0
    pending: int = 0
    pending_count: int = 0
    refunds: int = 0
    reversals: int = 0
    expenses: int = 0
    business_sales_count: int = 0
    family_transfers_count: int = 0
    expenses_count: int = 0
    sources: dict = field(default_factory=lambda: {
        "business_sales": [], "family_transfers": [], "expenses": [], "refunds": [], "reversals": [], "pending": [],
    })

    @property
    def profit(self) -> int:
        return self.business_sales - self.expenses

    @property
    def reconciliation_ok(self) -> bool:
        return self.total_collections == (
            self.business_sales + self.family_transfers + self.pending + self.refunds + self.reversals
        )


def compute(conn: sqlite3.Connection, merchant_id: str, start: date, end: date) -> Buckets:
    b = Buckets()
    s, e = start.isoformat(), end.isoformat()
    for p in conn.execute(PAYMENTS_SQL, (merchant_id, s, e)).fetchall():
        g, r = p["g"], p["r"]
        b.total_collections += g
        if p["reversed"]:
            b.reversals += g
            rev = conn.execute("SELECT ledger_entry_id FROM ledger_entries WHERE source_type = 'REVERSAL'"
                               " AND source_id = ? AND entry_type = 'REVERSAL'", (p["transaction_id"],)).fetchone()
            if rev:
                b.sources["reversals"].append(rev["ledger_entry_id"])
            continue
        if r:
            b.refunds += r
            b.sources["refunds"] += [x["ledger_entry_id"] for x in conn.execute(REFUND_ENTRIES_SQL, (p["transaction_id"],))]
        net = g - r
        cls = p["classification"]
        if cls == "SALE":
            b.business_sales += net
            b.business_sales_count += 1
            b.sources["business_sales"].append(p["class_entry_id"])
        elif cls == "FAMILY":
            b.family_transfers += net
            b.family_transfers_count += 1
            b.sources["family_transfers"].append(p["class_entry_id"])
        else:
            b.pending += net
            b.pending_count += 1
            b.sources["pending"].append(p["class_entry_id"])
    for x in conn.execute(EXPENSES_SQL, (merchant_id, s, e)).fetchall():
        b.expenses += x["amount_paise"]
        b.expenses_count += 1
        b.sources["expenses"].append(x["ledger_entry_id"])
    return b
