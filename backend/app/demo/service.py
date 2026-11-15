"""Demo tools (contract section 1): reset from data/demo/seed.db and inject the scripted demo-day payments.

next-payment goes through exactly the same code path as POST /payments.
"""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from .. import db, errors, money, repo
from ..config import DEMO_DATA_DIR, get_settings
from ..schemas import PaymentIn
from ..services import payments

SCRIPT_MERCHANTS = ("M001", "M002")


@lru_cache
def script(merchant_id: str) -> dict | None:
    path = DEMO_DATA_DIR / f"{merchant_id}_demo_day.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _injected(conn: sqlite3.Connection, transaction_id: str) -> bool:
    return conn.execute("SELECT 1 FROM payments WHERE transaction_id = ?", (transaction_id,)).fetchone() is not None


def reset(db_path: Path) -> dict:
    """Restore the committed seed with SQLite's backup API (safe with WAL and open connections)."""
    seed = get_settings().demo_seed_db
    if not seed.exists():
        raise errors.invalid_state(f"{seed.name} not found. Run python -m data.seed_demo first.", reason="NO_SEED")
    src = sqlite3.connect(f"file:{seed.as_posix()}?mode=ro", uri=True)
    dst = db.connect(db_path)
    try:
        src.backup(dst)
        merchants = repo.merchant_ids(dst)
        pending = {}
        for mid in SCRIPT_MERCHANTS:
            s = script(mid)
            if s is not None and mid in merchants:
                pending[mid] = sum(1 for i in s["payments"] if not _injected(dst, i["request"]["transaction_id"]))
    finally:
        src.close()
        dst.close()
    return {"status": "reset", "merchants": merchants, "demo_date": get_settings().demo_date.isoformat(),
            "pending_demo_payments": pending}


def _require_script(merchant_id: str) -> dict:
    s = script(merchant_id)
    if s is None:
        raise errors.not_found(f"No demo script for {merchant_id}", merchant_id=merchant_id)
    return s


def next_payment(conn: sqlite3.Connection, merchant_id: str) -> dict:
    repo.require_merchant_in_body(conn, merchant_id)
    s = _require_script(merchant_id)
    items = s["payments"]
    todo = [i for i in items if not _injected(conn, i["request"]["transaction_id"])]
    if not todo:
        raise errors.invalid_state("Demo script finished for this merchant", merchant_id=merchant_id)
    item = todo[0]
    _, body = payments.create_payment(conn, PaymentIn(**item["request"]))
    with db.write_tx(conn):
        conn.execute(
            "INSERT INTO demo_state (merchant_id, next_demo_index) VALUES (?, ?)"
            " ON CONFLICT(merchant_id) DO UPDATE SET next_demo_index = excluded.next_demo_index",
            (merchant_id, item["demo_index"] + 1),
        )
    return {**body, "demo_index": item["demo_index"], "demo_remaining": len(todo) - 1}


def script_view(conn: sqlite3.Connection, merchant_id: str) -> dict:
    repo.require_merchant(conn, merchant_id)
    s = _require_script(merchant_id)
    return {
        "merchant_id": merchant_id,
        "items": [
            {
                "demo_index": i["demo_index"],
                "transaction_id": i["request"]["transaction_id"],
                "time": i["request"]["timestamp"][11:16],
                "payer_name": i["request"]["payer_name"],
                "amount_display": money.display(i["request"]["amount_paise"]),
                "expected_action": i["expected_action"],
                "expected_classification": i["expected_final_classification"],
                "injected": _injected(conn, i["request"]["transaction_id"]),
            }
            for i in s["payments"]
        ],
    }
