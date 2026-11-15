"""Payments, questions and confirmation (contract sections 3-4, DATA_AND_LOGIC 5.6, 6, 7)."""
from __future__ import annotations

import json
import sqlite3

from .. import clock, db, errors, money, repo
from ..classifier.decide import decide
from ..feedback.memory import payer_counts
from ..ledger import writer as ledger
from ..questions_text import question_text, question_text_en
from ..schemas import ConfirmIn, PaymentIn, RefundIn, ReversalIn


# --- create -------------------------------------------------------------------------
def _normalized_body(req: PaymentIn) -> dict:
    body = req.model_dump(mode="json")
    body["timestamp"] = clock.iso(clock.parse(req.timestamp))
    return body


def _stored_body(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    payer = conn.execute("SELECT * FROM payers WHERE payer_id = ?", (row["payer_id"],)).fetchone()
    return {
        "transaction_id": row["transaction_id"], "merchant_id": row["merchant_id"], "payer_id": row["payer_id"],
        "payer_name": payer["payer_name"], "payer_vpa_kind": payer["payer_vpa_kind"],
        "amount_paise": row["amount_paise"], "payment_type": row["payment_type"],
        "timestamp": row["timestamp"], "description": row["description"],
    }


def create_payment(conn: sqlite3.Connection, req: PaymentIn) -> tuple[int, dict]:
    """201 new, 200 identical replay, 409 same transaction_id with different content."""
    body = _normalized_body(req)
    phash = repo.payload_hash(body)
    with db.write_tx(conn):
        existing = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (req.transaction_id,)).fetchone()
        if existing is not None:
            if existing["payload_hash"] == phash:
                return 200, payment_response(conn, req.transaction_id, replay=True)
            field = repo.first_difference(_stored_body(conn, existing), body)
            raise errors.duplicate_conflict(
                f"transaction_id {req.transaction_id} already exists with a different {field}",
                transaction_id=req.transaction_id, field=field,
            )
        repo.require_merchant_in_body(conn, req.merchant_id)
        repo.ensure_payer(conn, req.payer_id, req.payer_name, req.payer_vpa_kind)
        d = decide(conn, merchant_id=req.merchant_id, payer_id=req.payer_id, payer_vpa_kind=req.payer_vpa_kind,
                   amount_paise=req.amount_paise, payment_type=req.payment_type, timestamp=body["timestamp"],
                   transaction_id=req.transaction_id)
        now = clock.iso(clock.now())
        conn.execute(
            "INSERT INTO payments (transaction_id, merchant_id, payer_id, amount_paise, payment_type, timestamp,"
            " description, payload_hash, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (req.transaction_id, req.merchant_id, req.payer_id, req.amount_paise, req.payment_type,
             body["timestamp"], req.description, phash, now),
        )
        conn.execute(
            "INSERT INTO predictions (transaction_id, model_version, threshold, q_model, p_final, confidence,"
            " confidence_kind, suggested_classification, action, classification_source, reasons_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (req.transaction_id, d.model_version, d.threshold, d.q_model, d.p_final, d.confidence,
             d.confidence_kind, d.suggested, d.action, d.source, json.dumps(d.reasons), now),
        )
        ledger.append(
            conn, merchant_id=req.merchant_id, entry_type="PAYMENT_IN", source_type="PAYMENT",
            source_id=req.transaction_id, amount_paise=req.amount_paise, effective_at=body["timestamp"],
            classification=d.classification, classification_source=d.source, confidence=d.confidence,
        )
        if d.action == "ASK_MERCHANT":
            qid = repo.next_id(conn, "questions", "question_id", f"Q-{req.merchant_id}-")
            conn.execute(
                "INSERT INTO questions (question_id, merchant_id, transaction_id, status, created_at)"
                " VALUES (?, ?, ?, 'OPEN', ?)",
                (qid, req.merchant_id, req.transaction_id, now),
            )
    return 201, payment_response(conn, req.transaction_id, replay=False)


def payment_response(conn: sqlite3.Connection, transaction_id: str, *, replay: bool) -> dict:
    """The POST /payments response, rebuilt from what was stored at creation time."""
    p = conn.execute(
        "SELECT p.*, pr.* FROM payments p JOIN predictions pr USING (transaction_id) WHERE p.transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    entry = conn.execute(
        "SELECT ledger_entry_id, classification FROM ledger_entries"
        " WHERE source_type = 'PAYMENT' AND source_id = ? AND entry_type = 'PAYMENT_IN'",
        (transaction_id,),
    ).fetchone()
    q = conn.execute("SELECT question_id FROM questions WHERE transaction_id = ?", (transaction_id,)).fetchone()
    return {
        "transaction_id": transaction_id,
        "merchant_id": p["merchant_id"],
        "amount_paise": p["amount_paise"],
        "amount_display": money.display(p["amount_paise"]),
        "classification": entry["classification"],
        "suggested_classification": p["suggested_classification"],
        "confidence": p["confidence"],
        "confidence_kind": p["confidence_kind"],
        "action": p["action"],
        "classification_source": p["classification_source"],
        "reasons": json.loads(p["reasons_json"])[:4],
        "question_id": q["question_id"] if q else None,
        "ledger_entry_id": entry["ledger_entry_id"],
        "idempotent_replay": replay,
    }


# --- read ---------------------------------------------------------------------------
def payment_detail(conn: sqlite3.Connection, transaction_id: str) -> dict:
    p = conn.execute(
        "SELECT p.*, py.payer_name, py.payer_vpa_kind, pr.suggested_classification, pr.confidence,"
        " pr.action, pr.classification_source FROM payments p JOIN payers py USING (payer_id)"
        " JOIN predictions pr USING (transaction_id) WHERE p.transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    if p is None:
        raise errors.not_found(f"Unknown transaction {transaction_id}", transaction_id=transaction_id)
    history = conn.execute(
        "SELECT ledger_entry_id, entry_type, classification, classification_source, created_at FROM ledger_entries"
        " WHERE source_type = 'PAYMENT' AND source_id = ? AND entry_type IN ('PAYMENT_IN', 'RECLASSIFICATION')"
        " ORDER BY seq",
        (transaction_id,),
    ).fetchall()
    refunded = conn.execute(
        "SELECT COALESCE(SUM(amount_paise), 0) FROM refunds WHERE transaction_id = ?", (transaction_id,)
    ).fetchone()[0]
    reversed_ = conn.execute("SELECT 1 FROM reversals WHERE transaction_id = ?", (transaction_id,)).fetchone()
    return {
        "transaction_id": transaction_id,
        "merchant_id": p["merchant_id"],
        "payer_id": p["payer_id"],
        "payer_name": p["payer_name"],
        "payer_vpa_kind": p["payer_vpa_kind"],
        "payment_type": p["payment_type"],
        "amount_paise": p["amount_paise"],
        "amount_display": money.display(p["amount_paise"]),
        "timestamp": p["timestamp"],
        "description": p["description"],
        "current_classification": history[-1]["classification"],
        "initial_prediction": {
            "suggested_classification": p["suggested_classification"],
            "confidence": p["confidence"],
            "action": p["action"],
            "classification_source": p["classification_source"],
        },
        "classification_history": [
            {"ledger_entry_id": h["ledger_entry_id"], "entry_type": h["entry_type"],
             "classification": h["classification"], "source": h["classification_source"], "at": h["created_at"]}
            for h in history
        ],
        "refunded_paise": refunded,
        "reversed": reversed_ is not None,
    }


def list_questions(conn: sqlite3.Connection, merchant_id: str, *, status: str, date: str | None,
                   language: str | None) -> dict:
    merchant = repo.require_merchant(conn, merchant_id)
    lang = language or merchant["preferred_language"]
    sql = (
        "SELECT q.question_id, q.transaction_id, q.status, py.payer_name, p.amount_paise, p.timestamp,"
        " pr.suggested_classification, pr.confidence FROM questions q"
        " JOIN payments p USING (transaction_id) JOIN payers py ON py.payer_id = p.payer_id"
        " JOIN predictions pr ON pr.transaction_id = q.transaction_id"
        " WHERE q.merchant_id = ? AND q.status = ?"
    )
    args: list = [merchant_id, status]
    if date is not None:
        sql += " AND substr(p.timestamp, 1, 10) = ?"
        args.append(date)
    sql += " ORDER BY p.timestamp DESC, q.question_id DESC"
    items = [
        {
            "question_id": r["question_id"],
            "transaction_id": r["transaction_id"],
            "payer_name": r["payer_name"],
            "amount_paise": r["amount_paise"],
            "amount_display": money.display(r["amount_paise"]),
            "timestamp": r["timestamp"],
            "suggested_classification": r["suggested_classification"],
            "confidence": r["confidence"],
            "question_text": question_text(r["payer_name"], r["amount_paise"], lang),
            "question_text_en": question_text_en(r["payer_name"], r["amount_paise"]),
            "question_audio_id": None,  # TTS wiring comes with the voice module
            "status": r["status"],
        }
        for r in conn.execute(sql, args)
    ]
    return {"merchant_id": merchant_id, "items": items}


# --- confirm (correction workflow, contract section 4) -------------------------------
def confirm(conn: sqlite3.Connection, transaction_id: str, req: ConfirmIn) -> tuple[int, dict]:
    with db.write_tx(conn):
        pay = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (transaction_id,)).fetchone()
        if pay is None or pay["merchant_id"] != req.merchant_id:
            raise errors.not_found(f"Unknown transaction {transaction_id} for merchant {req.merchant_id}",
                                   transaction_id=transaction_id)
        if req.question_id is not None:
            q = conn.execute("SELECT * FROM questions WHERE question_id = ?", (req.question_id,)).fetchone()
            if q is None or q["transaction_id"] != transaction_id or q["merchant_id"] != req.merchant_id:
                raise errors.invalid_state(
                    f"question {req.question_id} does not belong to transaction {transaction_id}",
                    reason="QUESTION_MISMATCH", question_id=req.question_id,
                )
        if conn.execute("SELECT 1 FROM reversals WHERE transaction_id = ?", (transaction_id,)).fetchone():
            raise errors.invalid_state("Payment was reversed and cannot be confirmed", reason="REVERSED",
                                       transaction_id=transaction_id)

        if req.remember_payer and req.confirmed_category == "SALE" and pay["payment_type"] != "P2P":
            raise errors.validation_error("'Remember as customer' is only offered after a SALE answer on a P2P payment",
                                          field="remember_payer")

        current = ledger.current_classification_entry(conn, transaction_id)
        payer_id = pay["payer_id"]

        if current["classification"] == req.confirmed_category and current["classification_source"] == "MERCHANT_CONFIRMED":
            fb = conn.execute("SELECT feedback_id FROM feedback WHERE transaction_id = ? ORDER BY feedback_id DESC"
                              " LIMIT 1", (transaction_id,)).fetchone()
            return 200, _confirm_response(conn, pay, req, previous=current["classification"],
                                          ledger_entry_id=current["ledger_entry_id"],
                                          feedback_id=fb["feedback_id"] if fb else None, replay=True, moved_from=None)

        entry = ledger.append(
            conn, merchant_id=req.merchant_id, entry_type="RECLASSIFICATION", source_type="PAYMENT",
            source_id=transaction_id, amount_paise=pay["amount_paise"], effective_at=pay["timestamp"],
            supersedes_entry_id=current["ledger_entry_id"], classification=req.confirmed_category,
            classification_source="MERCHANT_CONFIRMED", confidence=None,
        )
        q_model = conn.execute("SELECT q_model FROM predictions WHERE transaction_id = ?",
                               (transaction_id,)).fetchone()["q_model"]
        feedback_id = repo.next_id(conn, "feedback", "feedback_id", f"FB-{req.merchant_id}-")
        conn.execute(
            "INSERT INTO feedback (feedback_id, merchant_id, transaction_id, payer_id, confirmed_category,"
            " previous_classification, q_model, channel, utterance_text, remember_payer, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (feedback_id, req.merchant_id, transaction_id, payer_id, req.confirmed_category,
             current["classification"], q_model, req.channel, req.utterance_text, int(req.remember_payer),
             entry["created_at"]),
        )
        conn.execute(
            "UPDATE questions SET status = 'ANSWERED', answered_at = ? WHERE transaction_id = ? AND status = 'OPEN'",
            (entry["created_at"], transaction_id),
        )
        moved_from = _remember(conn, req, payer_id, entry["created_at"]) if req.remember_payer else None
        return 201, _confirm_response(conn, pay, req, previous=current["classification"],
                                      ledger_entry_id=entry["ledger_entry_id"], feedback_id=feedback_id,
                                      replay=False, moved_from=moved_from)


def _remember(conn: sqlite3.Connection, req: ConfirmIn, payer_id: str, at: str) -> str | None:
    """Add the payer to the family or customer list. A payer is never in both: remembering in one list removes
    them from the other in the same transaction. Returns the list they were moved from. History is untouched."""
    if req.confirmed_category == "FAMILY":
        moved = "CUSTOMER" if repo.is_customer_payer(conn, req.merchant_id, payer_id) else None
        repo.remove_customer_payer(conn, req.merchant_id, payer_id)
        repo.add_family_payer(conn, req.merchant_id, payer_id, None, at, "CONFIRMATION")
    else:
        moved = "FAMILY" if repo.is_family_payer(conn, req.merchant_id, payer_id) else None
        repo.remove_family_payer(conn, req.merchant_id, payer_id)
        repo.add_customer_payer(conn, req.merchant_id, payer_id, at, "CONFIRMATION")
    return moved


def _confirm_response(conn, pay, req: ConfirmIn, *, previous, ledger_entry_id, feedback_id, replay, moved_from) -> dict:
    q = conn.execute("SELECT question_id, status FROM questions WHERE transaction_id = ?",
                     (pay["transaction_id"],)).fetchone()
    n_family, n_sale = payer_counts(conn, req.merchant_id, pay["payer_id"])
    configured = repo.is_family_payer(conn, req.merchant_id, pay["payer_id"])
    customer = repo.is_customer_payer(conn, req.merchant_id, pay["payer_id"])
    out = {
        "transaction_id": pay["transaction_id"],
        "previous_classification": previous,
        "confirmed_category": req.confirmed_category,
        "ledger_entry_id": ledger_entry_id,
        "feedback_id": feedback_id,
        "question_id": q["question_id"] if q else None,
        "question_status": q["status"] if q else None,
        "payer_memory": {
            "payer_id": pay["payer_id"],
            "confirmed_family": n_family,
            "confirmed_sale": n_sale,
            "family_payer_configured": configured,
            "customer_payer_configured": customer,
        },
        "moved_from": moved_from,
        "idempotent_replay": replay,
    }
    if configured and req.confirmed_category == "SALE":
        out["suggest_unconfigure"] = True
    return out


# --- list (contract section 3) -------------------------------------------------------
LIST_SQL = """
SELECT p.transaction_id, p.timestamp, py.payer_name, p.amount_paise, pr.confidence,
       le.classification AS current_classification, le.classification_source
FROM payments p
JOIN payers py ON py.payer_id = p.payer_id
JOIN predictions pr ON pr.transaction_id = p.transaction_id
JOIN ledger_entries le ON le.ledger_entry_id = (
    SELECT l2.ledger_entry_id FROM ledger_entries l2
    WHERE l2.source_type = 'PAYMENT' AND l2.source_id = p.transaction_id
      AND l2.entry_type IN ('PAYMENT_IN', 'RECLASSIFICATION')
    ORDER BY l2.seq DESC LIMIT 1)
WHERE p.merchant_id = ? AND substr(p.timestamp, 1, 10) BETWEEN ? AND ?
"""


def list_payments(conn: sqlite3.Connection, merchant_id: str, start, end, classification: str | None,
                  limit: int, offset: int) -> dict:
    """confidence = initial prediction's confidence; classification_source = current source (CHANGES 2026-11-14)."""
    repo.require_merchant(conn, merchant_id)
    sql, args = LIST_SQL, [merchant_id, start.isoformat(), end.isoformat()]
    if classification:
        sql += " AND le.classification = ?"
        args.append(classification)
    total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", args).fetchone()[0]
    rows = conn.execute(sql + " ORDER BY p.timestamp, p.transaction_id LIMIT ? OFFSET ?", [*args, limit, offset])
    items = [
        {
            "transaction_id": r["transaction_id"], "timestamp": r["timestamp"], "payer_name": r["payer_name"],
            "amount_paise": r["amount_paise"], "amount_display": money.display(r["amount_paise"]),
            "current_classification": r["current_classification"], "confidence": r["confidence"],
            "classification_source": r["classification_source"],
        }
        for r in rows
    ]
    return {"merchant_id": merchant_id, "count": total, "items": items}


# --- refunds and reversals (contract section 3; a payment has refunds or a reversal, never both) ---
def _refunded(conn: sqlite3.Connection, transaction_id: str) -> int:
    return conn.execute("SELECT COALESCE(SUM(amount_paise), 0) FROM refunds WHERE transaction_id = ?",
                        (transaction_id,)).fetchone()[0]


def refund(conn: sqlite3.Connection, transaction_id: str, req: RefundIn) -> tuple[int, dict]:
    body = req.model_dump(mode="json") | {"transaction_id": transaction_id,
                                         "timestamp": clock.iso(clock.parse(req.timestamp))}
    phash = repo.payload_hash(body)
    with db.write_tx(conn):
        pay = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (transaction_id,)).fetchone()
        if pay is None:
            raise errors.not_found(f"Unknown transaction {transaction_id}", transaction_id=transaction_id)
        existing = conn.execute("SELECT * FROM refunds WHERE refund_id = ?", (req.refund_id,)).fetchone()
        if existing is not None:
            if existing["payload_hash"] != phash:
                raise errors.duplicate_conflict(f"refund_id {req.refund_id} already exists with different content",
                                                refund_id=req.refund_id)
            return 200, _refund_response(conn, pay, req.refund_id)
        if conn.execute("SELECT 1 FROM reversals WHERE transaction_id = ?", (transaction_id,)).fetchone():
            raise errors.invalid_state("Payment was reversed and cannot be refunded", reason="REVERSED")
        if clock.parse(body["timestamp"]) < clock.parse(pay["timestamp"]):
            raise errors.validation_error("Refund is earlier than the payment", field="timestamp")
        remaining = pay["amount_paise"] - _refunded(conn, transaction_id)
        if req.amount_paise > remaining:
            raise errors.invalid_state("Refund is larger than the remaining refundable amount",
                                       reason="EXCEEDS_REMAINING", remaining_refundable_paise=remaining)
        conn.execute(
            "INSERT INTO refunds (refund_id, transaction_id, amount_paise, timestamp, reason, payload_hash)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (req.refund_id, transaction_id, req.amount_paise, body["timestamp"], req.reason, phash),
        )
        ledger.append(conn, merchant_id=pay["merchant_id"], entry_type="REFUND_OUT", source_type="REFUND",
                      source_id=req.refund_id, amount_paise=req.amount_paise, effective_at=body["timestamp"])
    return 201, _refund_response(conn, pay, req.refund_id)


def _refund_response(conn, pay, refund_id: str) -> dict:
    entry = conn.execute("SELECT ledger_entry_id FROM ledger_entries WHERE source_type = 'REFUND' AND source_id = ?",
                         (refund_id,)).fetchone()
    return {"refund_id": refund_id, "ledger_entry_id": entry["ledger_entry_id"],
            "remaining_refundable_paise": pay["amount_paise"] - _refunded(conn, pay["transaction_id"])}


def reverse(conn: sqlite3.Connection, transaction_id: str, req: ReversalIn) -> tuple[int, dict]:
    ts = clock.iso(clock.parse(req.timestamp))
    with db.write_tx(conn):
        pay = conn.execute("SELECT * FROM payments WHERE transaction_id = ?", (transaction_id,)).fetchone()
        if pay is None:
            raise errors.not_found(f"Unknown transaction {transaction_id}", transaction_id=transaction_id)
        if conn.execute("SELECT 1 FROM reversals WHERE transaction_id = ?", (transaction_id,)).fetchone():
            return 200, _reversal_response(conn, transaction_id)  # idempotent per transaction
        if _refunded(conn, transaction_id):
            raise errors.invalid_state("Payment has refunds and cannot be reversed", reason="HAS_REFUNDS")
        if clock.parse(ts) < clock.parse(pay["timestamp"]):
            raise errors.validation_error("Reversal is earlier than the payment", field="timestamp")
        conn.execute("INSERT INTO reversals (transaction_id, timestamp, reason) VALUES (?, ?, ?)",
                     (transaction_id, ts, req.reason))
        ledger.append(conn, merchant_id=pay["merchant_id"], entry_type="REVERSAL", source_type="REVERSAL",
                      source_id=transaction_id, amount_paise=pay["amount_paise"], effective_at=ts)
    return 201, _reversal_response(conn, transaction_id)


def _reversal_response(conn, transaction_id: str) -> dict:
    entry = conn.execute("SELECT ledger_entry_id FROM ledger_entries WHERE source_type = 'REVERSAL' AND source_id = ?",
                         (transaction_id,)).fetchone()
    return {"transaction_id": transaction_id, "ledger_entry_id": entry["ledger_entry_id"], "reversed": True}
