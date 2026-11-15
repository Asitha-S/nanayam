"""Demo tabs (UDHARI on): four of M001's regular customers with open tabs, written at startup and after /demo/reset.

They are regulars who never appear in the scripted demo day, so the judge tour is not interrupted by tab offers.
Ramesh N pays ₹2,000 on the first live payment of the day (LIVE_PAYER), leaving ₹300 after the merchant says yes.
Idempotent: each seed entry has a fixed client_request_id.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import clock, db, repo
from . import service

SEED: dict[str, list[tuple[str, str, list[tuple[int, str, str]]]]] = {
    "M001": [
        ("P10001", "Bhuvana", [(120000, "2026-11-03T19:10:00+05:30", "Function order")]),
        ("P10002", "Pooja A", [(85000, "2026-11-07T18:20:00+05:30", "Vegetables")]),
        ("P10006", "Ramesh N", [(150000, "2026-11-10T19:05:00+05:30", "Vegetables for the week"),
                                (80000, "2026-11-13T18:40:00+05:30", "Onions and tomatoes")]),
        ("P10005", "Murali K", [(46000, "2026-11-12T20:15:00+05:30", "Greens and lemons")]),
    ],
}
LIVE_PAYER = {"M001": ("P10006", 2000)}  # payer_id, rupees


def ensure(conn: sqlite3.Connection) -> int:
    """Write any missing seed entries. Returns how many were written."""
    if not service.enabled():
        return 0
    written = 0
    with db.write_tx(conn):
        for merchant_id, tabs in SEED.items():
            if repo.merchant(conn, merchant_id) is None:
                continue
            for payer_id, name, adds in tabs:
                repo.ensure_payer(conn, payer_id, name, "PERSONAL")
                for n, (paise, at, note) in enumerate(adds, start=1):
                    crid = f"seed-{merchant_id}-{payer_id}-{n}"
                    if conn.execute("SELECT 1 FROM tab_entries WHERE client_request_id = ?", (crid,)).fetchone():
                        continue
                    payload = {"seed": crid, "amount_paise": paise, "at": at}
                    service.insert_entry(conn, merchant_id=merchant_id, payer_id=payer_id, kind="ADD", amount_paise=paise,
                                         client_request_id=crid, input_source="SEED", payload=payload, effective_at=at,
                                         created_at=at, note=note)
                    written += 1
    return written


def ensure_path(db_path: Path) -> int:
    conn = db.connect(db_path)
    try:
        return ensure(conn)
    finally:
        conn.close()


def live_payer(conn: sqlite3.Connection, merchant_id: str) -> dict | None:
    """The live payment to send instead of a random one: the seeded customer paying part of the tab, once a day."""
    if not service.enabled() or merchant_id not in LIVE_PAYER:
        return None
    payer_id, rupees = LIVE_PAYER[merchant_id]
    d, _ = service.due(conn, merchant_id, payer_id)
    if d <= 0:
        return None
    today = clock.today().isoformat()
    if conn.execute("SELECT 1 FROM payments WHERE merchant_id = ? AND payer_id = ? AND substr(timestamp, 1, 10) = ?",
                    (merchant_id, payer_id, today)).fetchone():
        return None
    row = conn.execute("SELECT payer_name FROM payers WHERE payer_id = ?", (payer_id,)).fetchone()
    return {"payer_id": payer_id, "payer_name": row["payer_name"], "payer_vpa_kind": "PERSONAL", "role": "CUSTOMER",
            "amount_rupees": rupees, "payment_type": "P2M"}
