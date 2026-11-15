"""Payer memory (DATA_AND_LOGIC section 6): counts of merchant-confirmed labels for a payer.

Only rows in `feedback` count (merchant answers). The latest answer per transaction wins, and
reversed payments are excluded. Auto-classifications never count.
"""
from __future__ import annotations

import sqlite3

LATEST_FEEDBACK_SQL = """
SELECT f.transaction_id, f.confirmed_category
FROM feedback f
WHERE f.merchant_id = ? AND f.payer_id = ?
  AND f.feedback_id = (SELECT f2.feedback_id FROM feedback f2
                       WHERE f2.transaction_id = f.transaction_id ORDER BY f2.feedback_id DESC LIMIT 1)
  AND NOT EXISTS (SELECT 1 FROM reversals v WHERE v.transaction_id = f.transaction_id)
"""


def payer_counts(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> tuple[int, int]:
    """(n_family, n_sale)"""
    rows = conn.execute(LATEST_FEEDBACK_SQL, (merchant_id, payer_id)).fetchall()
    n_family = sum(1 for r in rows if r["confirmed_category"] == "FAMILY")
    return n_family, len(rows) - n_family
