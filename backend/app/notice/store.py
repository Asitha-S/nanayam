"""Stored notices (DATA_AND_LOGIC 1.1 `notices`). Shared contract between analyse() and evidence().

analyse() calls save_notice(...) with the `fields` object of its POST /notices/analyse response
({field: {"value", "origin", "confidence"}}); evidence() reads it back with load_notice().
"""
from __future__ import annotations

import json
import sqlite3

from .. import clock, db, errors, repo


def save_notice(conn: sqlite3.Connection, *, merchant_id: str, file_sha256: str, fields: dict,
                explanation_text: str | None = None) -> str:
    with db.write_tx(conn):
        repo.require_merchant_in_body(conn, merchant_id)
        notice_id = repo.next_id(conn, "notices", "notice_id", f"NTC-{merchant_id}-", width=3)
        conn.execute(
            "INSERT INTO notices (notice_id, merchant_id, file_sha256, fields_json, explanation_text, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (notice_id, merchant_id, file_sha256, json.dumps(fields, ensure_ascii=False), explanation_text,
             clock.iso(clock.now())),
        )
    return notice_id


def load_notice(conn: sqlite3.Connection, merchant_id: str, notice_id: str) -> dict:
    row = conn.execute("SELECT * FROM notices WHERE notice_id = ? AND merchant_id = ?", (notice_id, merchant_id)).fetchone()
    if row is None:
        raise errors.not_found(f"Unknown notice {notice_id} for {merchant_id}", notice_id=notice_id)
    return {"notice_id": row["notice_id"], "merchant_id": row["merchant_id"], "fields": json.loads(row["fields_json"])}
