"""Small shared repository helpers: lookups, ID allocation, setup inserts, payload hashing.

Append-only tables only ever get INSERTs (enforced by tests/test_append_only.py).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from . import errors


def payload_hash(body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def first_difference(stored: dict, incoming: dict) -> str:
    for key, value in incoming.items():
        if stored.get(key) != value:
            return key
    return "payload"


def next_id(conn: sqlite3.Connection, table: str, column: str, prefix: str, width: int = 6) -> str:
    """Next per-merchant ID like Q-M001-000214 (prefix 'Q-M001-')."""
    row = conn.execute(
        f"SELECT MAX(CAST(substr({column}, ?) AS INTEGER)) FROM {table} WHERE {column} LIKE ?",
        (len(prefix) + 1, prefix + "%"),
    ).fetchone()
    return f"{prefix}{(row[0] or 0) + 1:0{width}d}"


# --- merchants and payers ---------------------------------------------------------
def merchant(conn: sqlite3.Connection, merchant_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM merchants WHERE merchant_id = ?", (merchant_id,)).fetchone()


def require_merchant(conn: sqlite3.Connection, merchant_id: str) -> sqlite3.Row:
    """For path parameters: unknown merchant is 404."""
    row = merchant(conn, merchant_id)
    if row is None:
        raise errors.not_found(f"Unknown merchant {merchant_id}", merchant_id=merchant_id)
    return row


def require_merchant_in_body(conn: sqlite3.Connection, merchant_id: str) -> sqlite3.Row:
    """For request bodies: unknown merchant is 422 (contract section 3)."""
    row = merchant(conn, merchant_id)
    if row is None:
        raise errors.validation_error(f"Unknown merchant {merchant_id}", field="merchant_id")
    return row


def merchant_ids(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT merchant_id FROM merchants ORDER BY merchant_id")]


def is_family_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM merchant_family_payers WHERE merchant_id = ? AND payer_id = ?", (merchant_id, payer_id)
    ).fetchone() is not None


def is_customer_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM merchant_customer_payers WHERE merchant_id = ? AND payer_id = ?", (merchant_id, payer_id)
    ).fetchone() is not None


def add_customer_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str, added_at: str, added_via: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO merchant_customer_payers (merchant_id, payer_id, added_at, added_via) VALUES (?, ?, ?, ?)",
        (merchant_id, payer_id, added_at, added_via),
    )


def remove_family_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> None:
    """Configuration only: the ledger history is never touched."""
    conn.execute("DELETE FROM merchant_family_payers WHERE merchant_id = ? AND payer_id = ?", (merchant_id, payer_id))


def remove_customer_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> None:
    """Configuration only: the ledger history is never touched."""
    conn.execute("DELETE FROM merchant_customer_payers WHERE merchant_id = ? AND payer_id = ?", (merchant_id, payer_id))


def insert_merchant(conn: sqlite3.Connection, m: dict) -> None:
    conn.execute(
        "INSERT INTO merchants (merchant_id, display_name, owner_name, city, business_category, preferred_language, created_at)"
        " VALUES (:merchant_id, :display_name, :owner_name, :city, :business_category, :preferred_language, :created_at)",
        m,
    )


def ensure_payer(conn: sqlite3.Connection, payer_id: str, payer_name: str, payer_vpa_kind: str) -> None:
    """Payers are global; the first name/kind seen is kept."""
    conn.execute(
        "INSERT OR IGNORE INTO payers (payer_id, payer_name, payer_vpa_kind) VALUES (?, ?, ?)",
        (payer_id, payer_name, payer_vpa_kind),
    )


def add_family_payer(conn: sqlite3.Connection, merchant_id: str, payer_id: str, relation_label: str | None,
                     added_at: str, added_via: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO merchant_family_payers (merchant_id, payer_id, relation_label, added_at, added_via)"
        " VALUES (?, ?, ?, ?, ?)",
        (merchant_id, payer_id, relation_label, added_at, added_via),
    )
