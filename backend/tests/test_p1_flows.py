"""Real P1 endpoints on a seeded database: payments, questions, confirm (correction table),
expenses, summary with sources, ledger, demo reset / next-payment / script."""
import copy
import json
import sqlite3

import pytest

from app.config import DEMO_DATA_DIR, get_settings
from app.ledger.hashing import verify_chain

SCRIPT = json.loads((DEMO_DATA_DIR / "M001_demo_day.json").read_text(encoding="utf-8"))
EXPENSE = SCRIPT["expense"]
LAKSHMI_TXN = "TXN-M001-20261115-015"


def inject(c, n):
    out = []
    for _ in range(n):
        r = c.post("/api/demo/next-payment", json={"merchant_id": "M001"})
        assert r.status_code == 201, r.text
        out.append(r.json())
    return out


def summary(c, **params):
    return c.get("/api/merchants/M001/summary", params=params).json()


def amounts(s):
    return {k: s[k]["amount_paise"] for k in
            ("total_collections", "business_sales", "family_transfers", "pending", "expenses", "profit")} | {
        "pending_count": s["pending"]["count"]}


def ledger_rows():
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM ledger_entries WHERE merchant_id='M001' ORDER BY seq")]
    finally:
        conn.close()


def confirm(c, txn=LAKSHMI_TXN, **kw):
    body = {"merchant_id": "M001", "question_id": None, "confirmed_category": "FAMILY", "channel": "TAP",
            "utterance_text": None, "remember_payer": False} | kw
    return c.post(f"/api/payments/{txn}/confirm", json=body)


def ask_question_id(c):
    items = c.get("/api/merchants/M001/questions", params={"date": "2026-11-15"}).json()["items"]
    assert len(items) == 1
    return items[0]["question_id"]


# --- reset ------------------------------------------------------------------------
def test_reset_reports_pending_demo_payments(seeded):
    r = seeded.post("/api/demo/reset", json={}).json()
    assert r["status"] == "reset" and r["merchants"] == ["M001", "M002", "M003"]
    assert r["pending_demo_payments"] == {"M001": 15, "M002": 11} and r["demo_date"] == "2026-11-15"


def test_reset_without_seed_is_409(make_client, tmp_path):
    with make_client(DEMO_SEED_DB=str(tmp_path / "missing.db")) as c:
        r = c.post("/api/demo/reset", json={})
        assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "NO_SEED"


def test_reset_restores_seed_state(seeded):
    inject(seeded, 3)
    seeded.post("/api/expenses", json=EXPENSE)
    seeded.post("/api/demo/tamper", json={"merchant_id": "M001", "ledger_entry_id": "LE-M001-000001"})
    seeded.post("/api/demo/reset", json={})
    assert amounts(summary(seeded))["total_collections"] == 0 and amounts(summary(seeded))["expenses"] == 0
    assert seeded.get("/api/health").json()["tampered"] is False
    assert not any(i["injected"] for i in seeded.get("/api/demo/script", params={"merchant_id": "M001"}).json()["items"])


# --- the M001 demo day (DATA 3.3 rows 1-4, with the placeholder classifier) ------------
def test_demo_day_flow(seeded):
    r = seeded.post("/api/expenses", json=EXPENSE)
    assert r.status_code == 201 and r.json()["status"] == "RECORDED"
    s = summary(seeded)
    assert amounts(s) == {"total_collections": 0, "business_sales": 0, "family_transfers": 0, "pending": 0,
                          "expenses": 310000, "profit": -310000, "pending_count": 0}
    assert s["profit"]["amount_display"] == "−₹3,100" and s["reconciliation_ok"]

    sales = inject(seeded, 14)
    assert all(p["action"] == "AUTO_CLASSIFY" and p["classification"] == "SALE" for p in sales)
    assert [p["demo_index"] for p in sales] == list(range(1, 15)) and sales[-1]["demo_remaining"] == 1
    assert amounts(summary(seeded))["business_sales"] == 482000 and amounts(summary(seeded))["profit"] == 172000

    (ask,) = inject(seeded, 1)
    assert (ask["action"], ask["classification"], ask["suggested_classification"]) == ("ASK_MERCHANT", "PENDING", "FAMILY")
    assert ask["question_id"] and ask["demo_remaining"] == 0
    assert amounts(summary(seeded)) == {"total_collections": 682000, "business_sales": 482000, "family_transfers": 0,
                                        "pending": 200000, "expenses": 310000, "profit": 172000, "pending_count": 1}

    c = confirm(seeded, question_id=ask["question_id"], channel="VOICE", remember_payer=True)
    assert c.status_code == 201, c.text
    body = c.json()
    assert body["previous_classification"] == "PENDING" and body["question_status"] == "ANSWERED"
    assert body["payer_memory"] == {"payer_id": "P90001", "confirmed_family": 1, "confirmed_sale": 0,
                                    "family_payer_configured": True}
    after = summary(seeded)
    assert amounts(after) == {"total_collections": 682000, "business_sales": 482000, "family_transfers": 200000,
                              "pending": 0, "expenses": 310000, "profit": 172000, "pending_count": 0}
    assert after["reconciliation_ok"] and after["profit"]["label"] == "Recorded profit"
    assert "UPI payments only" in after["scope_note"]

    done = seeded.post("/api/demo/next-payment", json={"merchant_id": "M001"})
    assert done.status_code == 409 and done.json()["error"]["code"] == "INVALID_STATE"


def test_summary_sources_link_to_ledger_entries(seeded):
    seeded.post("/api/expenses", json=EXPENSE)
    inject(seeded, 15)
    qid = ask_question_id(seeded)
    confirm(seeded, question_id=qid)
    s = summary(seeded, include_sources="true")
    src = s["sources"]
    assert len(src["business_sales"]) == 14 and len(src["family_transfers"]) == 1 and len(src["expenses"]) == 1
    assert src["pending"] == src["refunds"] == src["reversals"] == []
    total = 0
    for entry_id in src["business_sales"]:
        e = seeded.get(f"/api/ledger/{entry_id}").json()
        assert e["classification"] == "SALE" and e["source"]["current_classification"] == "SALE"
        total += e["amount_paise"]
    assert total == s["business_sales"]["amount_paise"]
    fam = seeded.get(f"/api/ledger/{src['family_transfers'][0]}").json()
    assert fam["entry_type"] == "RECLASSIFICATION" and fam["classification_source"] == "MERCHANT_CONFIRMED"
    assert [h["classification"] for h in fam["source"]["classification_history"]] == ["PENDING", "FAMILY"]
    exp = seeded.get(f"/api/ledger/{src['expenses'][0]}").json()
    assert exp["source"]["amount_paise"] == 310000 and exp["expense_category"] == "STOCK_PURCHASE"
    assert summary(seeded)["sources"] is None


# --- questions ------------------------------------------------------------------------
def test_questions_filter_order_and_text(seeded):
    inject(seeded, 15)
    all_open = seeded.get("/api/merchants/M001/questions").json()["items"]
    assert [q["transaction_id"] for q in all_open] == [LAKSHMI_TXN, "TXN-M001-20261029-042"]  # newest first
    today = seeded.get("/api/merchants/M001/questions", params={"date": "2026-11-15"}).json()["items"]
    q = today[0]
    assert len(today) == 1 and q["status"] == "OPEN" and q["amount_display"] == "₹2,000"
    assert q["question_text"] == "Lakshmi R கிட்ட இருந்து 2,000 ரூபாய் வந்திருக்கு. இது கடை வியாபாரமா, வீட்டு பணமா?"
    assert q["question_text_en"] == "₹2,000 received from Lakshmi R. Is this a shop sale or family money?"
    te = seeded.get("/api/merchants/M001/questions", params={"date": "2026-11-15", "language": "te"}).json()
    assert "2,000 రూపాయలు" in te["items"][0]["question_text"]
    assert seeded.get("/api/merchants/M001/questions", params={"status": "ANSWERED"}).json()["items"] == []


def test_question_from_other_transaction_is_409(seeded):
    inject(seeded, 15)
    older = seeded.get("/api/merchants/M001/questions").json()["items"][1]["question_id"]
    r = confirm(seeded, question_id=older)
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "QUESTION_MISMATCH"
    assert confirm(seeded, question_id="Q-M001-999999").status_code == 409


# --- correction table (contract section 4) ----------------------------------------
def test_double_confirm_is_idempotent(seeded):
    inject(seeded, 15)
    qid = ask_question_id(seeded)
    first = confirm(seeded, question_id=qid)
    n = len(ledger_rows())
    again = confirm(seeded, question_id=qid)
    assert again.status_code == 200 and again.json()["idempotent_replay"] is True
    assert again.json()["ledger_entry_id"] == first.json()["ledger_entry_id"]
    assert again.json()["feedback_id"] == first.json()["feedback_id"]
    assert len(ledger_rows()) == n


def test_change_of_mind_is_a_new_correction(seeded):
    inject(seeded, 15)
    qid = ask_question_id(seeded)
    confirm(seeded, question_id=qid, confirmed_category="FAMILY")
    r = confirm(seeded, question_id=qid, confirmed_category="SALE")  # answered question, different category
    assert r.status_code == 201
    body = r.json()
    assert body["previous_classification"] == "FAMILY"
    assert body["payer_memory"]["confirmed_family"] == 0 and body["payer_memory"]["confirmed_sale"] == 1  # latest only
    assert "suggest_unconfigure" not in body
    s = amounts(summary(seeded))
    assert s["business_sales"] == 682000 and s["family_transfers"] == 0
    rows = ledger_rows()
    assert rows[-1]["supersedes_entry_id"] == rows[-2]["ledger_entry_id"]


def test_confirming_an_auto_decision_writes_merchant_confirmed(seeded):
    (p,) = inject(seeded, 1)
    r = confirm(seeded, txn=p["transaction_id"], confirmed_category="SALE")
    assert r.status_code == 201 and r.json()["previous_classification"] == "SALE" and r.json()["question_id"] is None
    detail = seeded.get(f"/api/payments/{p['transaction_id']}").json()
    assert [h["source"] for h in detail["classification_history"]] == ["MODEL", "MERCHANT_CONFIRMED"]


def test_configured_family_payer(seeded):
    r = seeded.post("/api/payments", json={
        "transaction_id": "TXN-M001-20261115-100", "merchant_id": "M001", "payer_id": "P90002",
        "payer_name": "Karthik", "payer_vpa_kind": "PERSONAL", "amount_paise": 150000, "payment_type": "P2P",
        "timestamp": "2026-11-15T20:00:00+05:30", "description": None,
    }).json()
    assert (r["classification"], r["action"], r["classification_source"]) == ("FAMILY", "AUTO_CLASSIFY", "MERCHANT_CONFIG")
    assert r["confidence"] is None and r["confidence_kind"] == "NONE"
    assert r["reasons"] == ["Marked as family by merchant"] and r["question_id"] is None
    corrected = confirm(seeded, txn="TXN-M001-20261115-100", confirmed_category="SALE").json()
    assert corrected["suggest_unconfigure"] is True and corrected["payer_memory"]["family_payer_configured"] is True


def test_remember_payer_applies_to_future_payments_only(seeded):
    inject(seeded, 15)
    confirm(seeded, question_id=ask_question_id(seeded), remember_payer=True)
    nxt = seeded.post("/api/payments", json={
        "transaction_id": "TXN-M001-20261115-101", "merchant_id": "M001", "payer_id": "P90001",
        "payer_name": "Lakshmi R", "payer_vpa_kind": "PERSONAL", "amount_paise": 200000, "payment_type": "P2P",
        "timestamp": "2026-11-15T20:30:00+05:30", "description": None,
    }).json()
    assert nxt["classification_source"] == "MERCHANT_CONFIG" and nxt["classification"] == "FAMILY"


def test_confirm_wrong_merchant_is_404(seeded):
    inject(seeded, 15)
    r = confirm(seeded, merchant_id="M002")
    assert r.status_code == 404


# --- idempotency (DATA 7.4) ----------------------------------------------------------
def test_payment_replay_and_conflict(seeded):
    req = copy.deepcopy(SCRIPT["payments"][14]["request"])
    first = seeded.post("/api/payments", json=req)
    replay = seeded.post("/api/payments", json=req)
    assert first.status_code == 201 and replay.status_code == 200
    assert replay.json() == first.json() | {"idempotent_replay": True}
    totals = amounts(summary(seeded))
    conflict = seeded.post("/api/payments", json=req | {"amount_paise": 210000})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "DUPLICATE_CONFLICT" and conflict.json()["error"]["details"]["field"] == "amount_paise"
    assert amounts(summary(seeded)) == totals


def test_every_demo_payment_twice_counts_once(seeded):
    for item in SCRIPT["payments"]:
        assert seeded.post("/api/payments", json=item["request"]).status_code == 201
        assert seeded.post("/api/payments", json=item["request"]).status_code == 200
    assert amounts(summary(seeded))["total_collections"] == 682000


def test_expense_idempotency(seeded):
    a = seeded.post("/api/expenses", json=EXPENSE)
    b = seeded.post("/api/expenses", json=EXPENSE)  # double tap: same draft id
    assert (a.status_code, b.status_code) == (201, 200)
    assert b.json() == a.json() | {"idempotent_replay": True}
    conflict = seeded.post("/api/expenses", json=EXPENSE | {"amount_paise": 320000})
    assert conflict.status_code == 409 and conflict.json()["error"]["details"]["field"] == "amount_paise"
    edited = seeded.post("/api/expenses", json=EXPENSE | {"client_request_id": "0e5c2a8e-1d7b-4c2e-9b9a-0c3d2e1f4a5b",
                                                         "amount_paise": 320000})
    assert edited.status_code == 201 and edited.json()["expense_id"] != a.json()["expense_id"]
    assert amounts(summary(seeded))["expenses"] == 630000


@pytest.mark.parametrize("timestamp", ["2026-11-15T21:30:00+05:30", "2026-11-07T05:40:00+05:30"])
def test_expense_time_window(seeded, timestamp):
    r = seeded.post("/api/expenses", json=EXPENSE | {"timestamp": timestamp})
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "timestamp"


def test_expense_future_check_uses_effective_now(seeded, wall_clock):
    wall_clock("12:00:00")
    inject(seeded, 15)  # payment 15 at 19:42 pushes the chain's created_at past 12:00
    ok = seeded.post("/api/expenses", json=EXPENSE | {"client_request_id": "1e5c2a8e-1d7b-4c2e-9b9a-0c3d2e1f4a5b",
                                                     "timestamp": "2026-11-15T19:00:00+05:30"})
    assert ok.status_code == 201


# --- ledger -----------------------------------------------------------------------------
def test_ledger_chain_and_created_at(seeded, wall_clock):
    wall_clock("12:00:00")
    seeded.post("/api/expenses", json=EXPENSE)
    inject(seeded, 15)
    confirm(seeded, question_id=ask_question_id(seeded))
    rows = ledger_rows()
    assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
    assert verify_chain(rows).status == "VALID"
    created = [r["created_at"] for r in rows]
    assert created == sorted(created)  # never goes backwards
    payment_15 = next(r for r in rows if r["source_id"] == LAKSHMI_TXN and r["entry_type"] == "PAYMENT_IN")
    assert payment_15["created_at"] == "2026-11-15T19:42:10+05:30"  # not 12:00, before the payment happened
    assert payment_15["confidence"] == "0.6000"  # 4 dp string in the database

    api = seeded.get("/api/merchants/M001/ledger").json()
    assert api["count"] == len(api["items"]) == 17  # expense + 15 payments + 1 reclassification today
    assert all(isinstance(i["confidence"], (float, type(None))) for i in api["items"])
    reclass = seeded.get("/api/merchants/M001/ledger", params={"entry_type": "RECLASSIFICATION"}).json()["items"]
    assert len(reclass) == 1 and reclass[0]["supersedes_entry_id"] == payment_15["ledger_entry_id"]
    history = seeded.get("/api/merchants/M001/ledger", params={"start_date": "2026-10-01", "end_date": "2026-10-31"}).json()
    assert {i["source_id"] for i in history["items"]} == {"TXN-M001-20261020-050", "TXN-M001-20261029-042"}


def test_ledger_entry_404(seeded):
    assert seeded.get("/api/ledger/LE-M001-999999").status_code == 404


def test_summary_period_validation(seeded):
    r = seeded.get("/api/merchants/M001/summary", params={"start_date": "2026-11-15", "end_date": "2026-11-01"})
    assert r.status_code == 422


def test_history_period_summary(seeded):
    s = summary(seeded, start_date="2026-10-01", end_date="2026-10-31")
    assert amounts(s) == {"total_collections": 500000, "business_sales": 0, "family_transfers": 200000,
                          "pending": 300000, "expenses": 0, "profit": 0, "pending_count": 1}


def test_demo_script_view(seeded):
    inject(seeded, 2)
    items = seeded.get("/api/demo/script", params={"merchant_id": "M001"}).json()["items"]
    assert len(items) == 15 and [i["injected"] for i in items[:3]] == [True, True, False]
    assert items[0]["payer_name"] == "Senthil K" and items[0]["amount_display"] == "₹40" and items[0]["time"] == "06:12"
    assert items[14]["expected_action"] == "ASK_MERCHANT"


def test_m002_demo_day(seeded):
    seeded.post("/api/expenses", json=json.loads((DEMO_DATA_DIR / "M002_demo_day.json").read_text(encoding="utf-8"))["expense"])
    for _ in range(11):
        last = seeded.post("/api/demo/next-payment", json={"merchant_id": "M002"}).json()
    assert last["action"] == "ASK_MERCHANT"
    confirm(seeded, txn=last["transaction_id"], merchant_id="M002", question_id=last["question_id"])
    s = seeded.get("/api/merchants/M002/summary").json()
    assert amounts(s) == {"total_collections": 785000, "business_sales": 635000, "family_transfers": 150000,
                          "pending": 0, "expenses": 420000, "profit": 215000, "pending_count": 0}


def test_health_reports_placeholder_model(seeded):
    assert seeded.get("/api/health").json()["model_version"] == "placeholder-rule-not-a-model"
