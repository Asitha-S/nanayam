"""The udhari book (contract section 13): tabs, ADD and SETTLE entries, offers, and payer matching for voice.

Append-only: an entry is never edited or deleted. A balance is computed from the entries, first-in first-out (a
SETTLE pays off the oldest ADD first), so `opened_at` is the oldest ADD not yet paid off.
"""
from __future__ import annotations

import sqlite3

from .. import clock, db, errors, money, repo
from ..config import get_settings
from . import names, texts

ADD_FIELDS = ("client_request_id", "merchant_id", "payer_id", "amount_paise", "note", "input_source", "language",
              "utterance_text", "voice_log_id")
SETTLE_FIELDS = ("client_request_id", "merchant_id", "payer_id", "transaction_id")
CANDIDATES = 6


def enabled() -> bool:
    return get_settings().udhari


def require_enabled() -> None:
    if not enabled():
        raise errors.not_found("Udhari is off on this server (UDHARI=false)", feature="udhari")


# ---- reading ---------------------------------------------------------------------------------------------------

def _rows(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tab_entries WHERE merchant_id = ? AND payer_id = ? ORDER BY effective_at, tab_entry_id",
                        (merchant_id, payer_id)).fetchall()


def _walk(rows) -> tuple[int, str | None, list[tuple[sqlite3.Row, int]]]:
    """(due, opened_at, [(entry, balance after)]) with first-in first-out settlement."""
    open_adds: list[list] = []  # [remaining paise, effective_at]
    balance = 0
    out = []
    for r in rows:
        amount = r["amount_paise"]
        if r["direction"] > 0:
            open_adds.append([amount, r["effective_at"]])
            balance += amount
        else:
            left = min(amount, balance)
            balance -= left
            while left and open_adds:
                take = min(left, open_adds[0][0])
                open_adds[0][0] -= take
                left -= take
                if open_adds[0][0] == 0:
                    open_adds.pop(0)
        out.append((r, balance))
    return balance, (open_adds[0][1] if open_adds else None), out


def due(conn: sqlite3.Connection, merchant_id: str, payer_id: str) -> tuple[int, str | None]:
    d, opened, _ = _walk(_rows(conn, merchant_id, payer_id))
    return d, opened


def _balance_before(conn: sqlite3.Connection, merchant_id: str, payer_id: str, entry_id: str) -> int:
    prev = 0
    for r, bal in _walk(_rows(conn, merchant_id, payer_id))[2]:
        if r["tab_entry_id"] == entry_id:
            return prev
        prev = bal
    return prev


def _payer(conn: sqlite3.Connection, payer_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT payer_id, payer_name FROM payers WHERE payer_id = ?", (payer_id,)).fetchone()
    if row is None:
        raise errors.not_found(f"Unknown payer {payer_id}", payer_id=payer_id)
    return row


def _payment_entry(conn: sqlite3.Connection, transaction_id: str) -> str | None:
    row = conn.execute("SELECT ledger_entry_id FROM ledger_entries WHERE source_type = 'PAYMENT' AND source_id = ?"
                       " AND entry_type = 'PAYMENT_IN'", (transaction_id,)).fetchone()
    return row["ledger_entry_id"] if row else None


def _used(conn: sqlite3.Connection, transaction_id: str) -> bool:
    return conn.execute("SELECT 1 FROM tab_entries WHERE kind = 'SETTLE' AND transaction_id = ?",
                        (transaction_id,)).fetchone() is not None


def _source(conn: sqlite3.Connection, r: sqlite3.Row) -> dict:
    kind = "PAYMENT" if r["kind"] == "SETTLE" else r["input_source"]
    return {"type": kind, "transaction_id": r["transaction_id"],
            "ledger_entry_id": _payment_entry(conn, r["transaction_id"]) if r["transaction_id"] else None,
            "utterance_text": r["utterance_text"], "voice_log_id": r["voice_log_id"]}


def _offer(conn: sqlite3.Connection, p: sqlite3.Row, payer_name: str, due_paise: int) -> dict:
    settle = min(p["amount_paise"], due_paise)
    return {"transaction_id": p["transaction_id"], "payer_id": p["payer_id"], "payer_name": payer_name,
            "timestamp": p["timestamp"], "amount_paise": p["amount_paise"], "amount_display": money.display(p["amount_paise"]),
            "ledger_entry_id": _payment_entry(conn, p["transaction_id"]), "due_paise": due_paise,
            "due_display": money.display(due_paise), "settle_paise": settle, "settle_display": money.display(settle)}


def list_tabs(conn: sqlite3.Connection, merchant_id: str, language: str | None) -> dict:
    require_enabled()
    m = repo.require_merchant(conn, merchant_id)
    lang = language or (m["preferred_language"] if m["preferred_language"] in ("ta", "te") else "ta")
    tabs = conn.execute("SELECT t.payer_id, py.payer_name FROM tabs t JOIN payers py USING (payer_id) WHERE t.merchant_id = ?",
                        (merchant_id,)).fetchall()
    items = []
    for t in tabs:
        d, opened, walked = _walk(_rows(conn, merchant_id, t["payer_id"]))
        items.append({
            "payer_id": t["payer_id"], "payer_name": t["payer_name"], "due_paise": d, "due_display": money.display(d),
            "opened_at": opened,
            "entries": [{"tab_entry_id": r["tab_entry_id"], "kind": r["kind"], "amount_paise": r["amount_paise"],
                         "amount_display": money.display(r["amount_paise"]), "balance_after_paise": bal,
                         "balance_after_display": money.display(bal), "created_at": r["effective_at"], "note": r["note"],
                         "source": _source(conn, r)} for r, bal in walked],
        })
    open_items = sorted((i for i in items if i["due_paise"] > 0), key=lambda i: (i["opened_at"], i["payer_name"]))
    settled = sorted((i for i in items if i["due_paise"] <= 0),
                     key=lambda i: i["entries"][-1]["created_at"] if i["entries"] else "", reverse=True)
    total = sum(i["due_paise"] for i in open_items)

    offers = []
    today = clock.today().isoformat()
    for i in open_items:
        for p in conn.execute("SELECT * FROM payments WHERE merchant_id = ? AND payer_id = ? AND substr(timestamp, 1, 10) = ?"
                              " AND timestamp >= ? ORDER BY timestamp DESC", (merchant_id, i["payer_id"], today, i["opened_at"])):
            if not _used(conn, p["transaction_id"]):
                offers.append(_offer(conn, p, i["payer_name"], i["due_paise"]))
    offers.sort(key=lambda o: o["timestamp"], reverse=True)
    return {
        "merchant_id": merchant_id, "as_of": clock.iso(clock.now()),
        "total_due_paise": total, "total_due_display": money.display(total), "open_count": len(open_items),
        "items": open_items + settled,
        "offers": offers,
        "spoken": {"language": lang, "text": texts.dues(lang, open_items, total)},
    }


def offer_for_payment(conn: sqlite3.Connection, transaction_id: str, language: str) -> dict | None:
    """The Soundbox's second card for a payment: only when the payer's tab is open and no SETTLE uses it yet."""
    p = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (transaction_id,)).fetchone()
    if p is None or _used(conn, transaction_id):
        return None
    d, opened = due(conn, p["merchant_id"], p["payer_id"])
    if d <= 0 or (opened and p["timestamp"] < opened):
        return None
    name = _payer(conn, p["payer_id"])["payer_name"]
    o = _offer(conn, p, name, d)
    text, text_en = texts.offer(language, name, p["amount_paise"], d)
    return {"payer_id": o["payer_id"], "payer_name": name, "payment_display": o["amount_display"],
            "due_paise": d, "due_display": o["due_display"], "settle_paise": o["settle_paise"],
            "settle_display": o["settle_display"], "text": text, "text_en": text_en}


# ---- writing ---------------------------------------------------------------------------------------------------

def _ensure_tab(conn: sqlite3.Connection, merchant_id: str, payer_id: str, at: str) -> str:
    tab_id = f"TABS-{merchant_id}-{payer_id}"
    conn.execute("INSERT OR IGNORE INTO tabs (tab_id, merchant_id, payer_id, created_at) VALUES (?, ?, ?, ?)",
                 (tab_id, merchant_id, payer_id, at))
    return tab_id


def insert_entry(conn: sqlite3.Connection, *, merchant_id: str, payer_id: str, kind: str, amount_paise: int,
                 client_request_id: str, input_source: str, payload: dict, effective_at: str, created_at: str,
                 transaction_id: str | None = None, note: str | None = None, language: str | None = None,
                 utterance_text: str | None = None, voice_log_id: str | None = None) -> str:
    """Insert-only (inside the caller's write_tx)."""
    tab_id = _ensure_tab(conn, merchant_id, payer_id, created_at)
    entry_id = repo.next_id(conn, "tab_entries", "tab_entry_id", f"TAB-{merchant_id}-")
    conn.execute(
        "INSERT INTO tab_entries (tab_entry_id, tab_id, merchant_id, payer_id, kind, amount_paise, direction, transaction_id,"
        " client_request_id, input_source, note, language, utterance_text, voice_log_id, payload_hash, effective_at,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entry_id, tab_id, merchant_id, payer_id, kind, amount_paise, -1 if kind == "SETTLE" else 1, transaction_id,
         client_request_id, input_source, note, language, utterance_text, voice_log_id, repo.payload_hash(payload),
         effective_at, created_at),
    )
    return entry_id


def _replay(conn: sqlite3.Connection, body: dict, fields: tuple[str, ...]) -> sqlite3.Row | None:
    """The stored entry for this client_request_id (same body), else None; a different body is 409."""
    existing = conn.execute("SELECT * FROM tab_entries WHERE client_request_id = ?", (body["client_request_id"],)).fetchone()
    if existing is None:
        return None
    if existing["payload_hash"] == repo.payload_hash(body):
        return existing
    stored = {k: existing[k] if k in existing.keys() else None for k in fields}
    field = repo.first_difference(stored, body)
    raise errors.duplicate_conflict(f"client_request_id {body['client_request_id']} already exists with a different {field}",
                                    client_request_id=body["client_request_id"], field=field)


def add(conn: sqlite3.Connection, payer_id: str, req) -> tuple[int, dict]:
    require_enabled()
    body = {**req.model_dump(mode="json"), "payer_id": payer_id}
    with db.write_tx(conn):
        done = _replay(conn, body, ADD_FIELDS)
        if done is None:
            repo.require_merchant_in_body(conn, req.merchant_id)
            _payer(conn, payer_id)
            now = clock.iso(clock.now())
            entry_id = insert_entry(conn, merchant_id=req.merchant_id, payer_id=payer_id, kind="ADD",
                                    amount_paise=req.amount_paise, client_request_id=body["client_request_id"],
                                    input_source=req.input_source, payload=body, effective_at=now, created_at=now,
                                    note=req.note, language=req.language, utterance_text=req.utterance_text,
                                    voice_log_id=req.voice_log_id)
        else:
            entry_id = done["tab_entry_id"]
    d, _ = due(conn, req.merchant_id, payer_id)
    name = _payer(conn, payer_id)["payer_name"]
    return (200 if done else 201), {
        "tab_entry_id": entry_id, "payer_id": payer_id, "payer_name": name, "kind": "ADD",
        "amount_paise": req.amount_paise, "amount_display": money.display(req.amount_paise),
        "due_paise": d, "due_display": money.display(d), "idempotent_replay": done is not None,
    }


def settle(conn: sqlite3.Connection, payer_id: str, req) -> tuple[int, dict]:
    """Take a payment off the tab: amount = min(payment, due now). The payment itself is untouched."""
    require_enabled()
    body = {**req.model_dump(mode="json"), "payer_id": payer_id}
    with db.write_tx(conn):
        done = _replay(conn, body, SETTLE_FIELDS)
        if done is None:
            repo.require_merchant_in_body(conn, req.merchant_id)
            _payer(conn, payer_id)
            p = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (req.transaction_id,)).fetchone()
            if p is None:
                raise errors.not_found(f"Unknown transaction {req.transaction_id}", transaction_id=req.transaction_id)
            if p["merchant_id"] != req.merchant_id or p["payer_id"] != payer_id:
                raise errors.validation_error("The payment is not from this payer to this merchant", field="transaction_id",
                                              transaction_id=req.transaction_id)
            if _used(conn, req.transaction_id):
                raise errors.invalid_state("This payment already settled a tab", reason="PAYMENT_ALREADY_USED",
                                           transaction_id=req.transaction_id)
            before, _ = due(conn, req.merchant_id, payer_id)
            if before <= 0:
                raise errors.invalid_state("Nothing is due on this tab", reason="NOTHING_DUE", payer_id=payer_id)
            amount = min(p["amount_paise"], before)
            now = clock.iso(clock.now())
            entry_id = insert_entry(conn, merchant_id=req.merchant_id, payer_id=payer_id, kind="SETTLE", amount_paise=amount,
                                    client_request_id=body["client_request_id"], input_source="PAYMENT", payload=body,
                                    effective_at=now, created_at=now, transaction_id=req.transaction_id)
            payment_paise = p["amount_paise"]
        else:
            entry_id, amount = done["tab_entry_id"], done["amount_paise"]
            payment_paise = conn.execute("SELECT amount_paise FROM payments WHERE transaction_id = ?",
                                         (req.transaction_id,)).fetchone()["amount_paise"]
            before = _balance_before(conn, req.merchant_id, payer_id, entry_id)
    after, _ = due(conn, req.merchant_id, payer_id)
    return (200 if done else 201), {
        "tab_entry_id": entry_id, "payer_id": payer_id, "payer_name": _payer(conn, payer_id)["payer_name"], "kind": "SETTLE",
        "transaction_id": req.transaction_id, "amount_paise": amount, "amount_display": money.display(amount),
        "payment_amount_display": money.display(payment_paise), "due_before_display": money.display(before),
        "due_paise": after, "due_display": money.display(after), "idempotent_replay": done is not None,
    }


# ---- voice: who is "ரமேஷ்"? -------------------------------------------------------------------------------------

def payer_candidates(conn: sqlite3.Connection, merchant_id: str, heard: str | None) -> tuple[dict | None, list[dict]]:
    """(best match or None, up to CANDIDATES [{payer_id, payer_name}]) among the merchant's tab payers and regular
    customers (personal payers who paid at least 5 times, not family)."""
    tab_ids = {r["payer_id"] for r in conn.execute("SELECT payer_id FROM tabs WHERE merchant_id = ?", (merchant_id,))}
    rows = conn.execute(
        "SELECT py.payer_id, py.payer_name, COUNT(p.transaction_id) AS n FROM payers py"
        " LEFT JOIN payments p ON p.payer_id = py.payer_id AND p.merchant_id = ?"
        " WHERE py.payer_vpa_kind = 'PERSONAL'"
        " AND py.payer_id NOT IN (SELECT payer_id FROM merchant_family_payers WHERE merchant_id = ?)"
        " GROUP BY py.payer_id HAVING n >= 5 OR py.payer_id IN (SELECT payer_id FROM tabs WHERE merchant_id = ?)",
        (merchant_id, merchant_id, merchant_id)).fetchall()
    ranked = sorted(rows, key=lambda r: (-(names.score(heard, r["payer_name"]) if heard else 0.0),
                                         r["payer_id"] not in tab_ids, -r["n"], r["payer_name"]))
    out = [{"payer_id": r["payer_id"], "payer_name": r["payer_name"]} for r in ranked[:CANDIDATES]]
    best = ranked[0] if ranked and heard and names.score(heard, ranked[0]["payer_name"]) >= names.MATCH_AT else None
    return ({"payer_id": best["payer_id"], "payer_name": best["payer_name"]} if best else None), out
