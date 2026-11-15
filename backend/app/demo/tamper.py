"""DEMO ONLY: edit one ledger entry's amount directly in SQLite WITHOUT updating hashes, so
/ledger/verify can show detection live (contract section 7). Imported only by the /demo/tamper route
(lazily), never by any other module. /demo/reset (restoring seed.db) undoes it.

This is the one file allowed to UPDATE ledger_entries (tests/test_append_only.py excludes it).
"""
from __future__ import annotations

import sqlite3

from .. import clock, db, errors
from .service import FLAGS_SQL


def tamper(conn: sqlite3.Connection, merchant_id: str, ledger_entry_id: str) -> None:
    with db.write_tx(conn):
        row = conn.execute("SELECT 1 FROM ledger_entries WHERE ledger_entry_id = ? AND merchant_id = ?",
                           (ledger_entry_id, merchant_id)).fetchone()
        if row is None:
            raise errors.not_found(f"Unknown ledger entry {ledger_entry_id} for {merchant_id}",
                                   ledger_entry_id=ledger_entry_id)
        conn.execute("UPDATE ledger_entries SET amount_paise = amount_paise + 100 WHERE ledger_entry_id = ?",
                     (ledger_entry_id,))
        conn.execute(FLAGS_SQL)
        conn.execute("INSERT OR REPLACE INTO demo_flags (name, value) VALUES ('tampered', ?)",
                     (f"{ledger_entry_id} at {clock.iso(clock.real_now())}",))

