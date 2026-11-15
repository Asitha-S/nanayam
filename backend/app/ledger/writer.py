"""Appending ledger entries (DATA_AND_LOGIC 7.1, 7.2). Call inside db.write_tx so seq has no gaps."""
from __future__ import annotations

import sqlite3

from .. import clock, money
from .hashing import GENESIS_PREV_HASH, compute_hash, confidence_from_db, confidence_to_db

COLUMNS = (
    "ledger_entry_id", "merchant_id", "seq", "entry_type", "source_type", "source_id", "supersedes_entry_id",
    "amount_paise", "classification", "classification_source", "confidence", "expense_category",
    "effective_at", "created_at", "prev_hash", "hash",
)


def last_entry(conn: sqlite3.Connection, merchant_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ledger_entries WHERE merchant_id = ? ORDER BY seq DESC LIMIT 1", (merchant_id,)
    ).fetchone()


def last_created_at(conn: sqlite3.Connection, merchant_id: str):
    last = last_entry(conn, merchant_id)
    return clock.parse(last["created_at"]) if last else None


def append(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    entry_type: str,
    source_type: str,
    source_id: str,
    amount_paise: int,
    effective_at: str,
    supersedes_entry_id: str | None = None,
    classification: str | None = None,
    classification_source: str | None = None,
    confidence: float | None = None,
    expense_category: str | None = None,
) -> dict:
    last = last_entry(conn, merchant_id)
    seq = 1 if last is None else last["seq"] + 1
    prev_created = clock.parse(last["created_at"]) if last else None
    row = {
        "ledger_entry_id": f"LE-{merchant_id}-{seq:06d}",
        "merchant_id": merchant_id,
        "seq": seq,
        "entry_type": entry_type,
        "source_type": source_type,
        "source_id": source_id,
        "supersedes_entry_id": supersedes_entry_id,
        "amount_paise": amount_paise,
        "classification": classification,
        "classification_source": classification_source,
        "confidence": confidence_to_db(confidence),
        "expense_category": expense_category,
        "effective_at": effective_at,
        "created_at": clock.iso(clock.created_at_for(clock.parse(effective_at), prev_created)),
        "prev_hash": GENESIS_PREV_HASH if last is None else last["hash"],
    }
    row["hash"] = compute_hash(row)
    conn.execute(
        f"INSERT INTO ledger_entries ({', '.join(COLUMNS)}) VALUES ({', '.join(':' + c for c in COLUMNS)})", row
    )
    return row


def to_api(row) -> dict:
    """DB row -> contract shape (confidence as a number, amount_display added)."""
    r = dict(row)
    return {
        "ledger_entry_id": r["ledger_entry_id"],
        "seq": r["seq"],
        "entry_type": r["entry_type"],
        "source_type": r["source_type"],
        "source_id": r["source_id"],
        "supersedes_entry_id": r["supersedes_entry_id"],
        "amount_paise": r["amount_paise"],
        "amount_display": money.display(r["amount_paise"]),
        "classification": r["classification"],
        "classification_source": r["classification_source"],
        "confidence": confidence_from_db(r["confidence"]),
        "expense_category": r["expense_category"],
        "effective_at": r["effective_at"],
        "created_at": r["created_at"],
        "prev_hash": r["prev_hash"],
        "hash": r["hash"],
    }


def current_classification_entry(conn: sqlite3.Connection, transaction_id: str) -> sqlite3.Row | None:
    """Latest PAYMENT_IN / RECLASSIFICATION entry for a payment (highest seq)."""
    return conn.execute(
        "SELECT * FROM ledger_entries WHERE source_type = 'PAYMENT' AND source_id = ?"
        " AND entry_type IN ('PAYMENT_IN', 'RECLASSIFICATION') ORDER BY seq DESC LIMIT 1",
        (transaction_id,),
    ).fetchone()
