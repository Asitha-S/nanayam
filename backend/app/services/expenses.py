"""Expenses (contract section 5). Idempotent on client_request_id."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from .. import clock, db, errors, money, repo
from ..ledger import writer as ledger
from ..schemas import ExpenseIn

MAX_DAYS_BACK = 7
STORED_FIELDS = ("client_request_id", "merchant_id", "amount_paise", "category", "description", "timestamp",
                 "input_source", "language", "utterance_text", "voice_log_id")


def check_expense_time(timestamp: str, prev_created_at=None) -> None:
    """Not in the future (vs the effective now) and not more than 7 days back."""
    ts = clock.parse(timestamp)
    now = clock.effective_now(prev_created_at)
    if ts > now:
        raise errors.validation_error("Expense timestamp is in the future", field="timestamp")
    if ts < now - timedelta(days=MAX_DAYS_BACK):
        raise errors.validation_error("Expense timestamp is more than 7 days back", field="timestamp")


def _normalized_body(req: ExpenseIn) -> dict:
    body = req.model_dump(mode="json")
    body["timestamp"] = clock.iso(clock.parse(req.timestamp))
    return body


def create_expense(conn: sqlite3.Connection, req: ExpenseIn) -> tuple[int, dict]:
    body = _normalized_body(req)
    phash = repo.payload_hash(body)
    with db.write_tx(conn):
        existing = conn.execute("SELECT * FROM expenses WHERE client_request_id = ?",
                                (body["client_request_id"],)).fetchone()
        if existing is not None:
            if existing["payload_hash"] == phash:
                return 200, _response(conn, existing["expense_id"], replay=True)
            field = repo.first_difference({k: existing[k] for k in STORED_FIELDS}, body)
            raise errors.duplicate_conflict(
                f"client_request_id {body['client_request_id']} already exists with a different {field}",
                client_request_id=body["client_request_id"], field=field,
            )
        repo.require_merchant_in_body(conn, req.merchant_id)
        check_expense_time(body["timestamp"], ledger.last_created_at(conn, req.merchant_id))
        expense_id = repo.next_id(conn, "expenses", "expense_id", f"EXP-{req.merchant_id}-")
        entry = ledger.append(
            conn, merchant_id=req.merchant_id, entry_type="EXPENSE", source_type="EXPENSE", source_id=expense_id,
            amount_paise=req.amount_paise, effective_at=body["timestamp"], expense_category=req.category,
        )
        conn.execute(
            f"INSERT INTO expenses (expense_id, {', '.join(STORED_FIELDS)}, payload_hash, created_at)"
            f" VALUES (?, {', '.join('?' for _ in STORED_FIELDS)}, ?, ?)",
            (expense_id, *(body[k] for k in STORED_FIELDS), phash, entry["created_at"]),
        )
    return 201, _response(conn, expense_id, replay=False)


def _response(conn: sqlite3.Connection, expense_id: str, *, replay: bool) -> dict:
    e = conn.execute("SELECT * FROM expenses WHERE expense_id = ?", (expense_id,)).fetchone()
    entry = conn.execute("SELECT ledger_entry_id FROM ledger_entries WHERE source_type = 'EXPENSE'"
                         " AND source_id = ? AND entry_type = 'EXPENSE'", (expense_id,)).fetchone()
    voided = conn.execute("SELECT 1 FROM expense_voids WHERE expense_id = ?", (expense_id,)).fetchone()
    return {
        "expense_id": expense_id,
        "ledger_entry_id": entry["ledger_entry_id"],
        "amount_paise": e["amount_paise"],
        "amount_display": money.display(e["amount_paise"]),
        "category": e["category"],
        "status": "VOIDED" if voided else "RECORDED",
        "idempotent_replay": replay,
    }
