"""DATA_AND_LOGIC 3.3 / 3.4 on the committed seed (data/demo/seed.db) via /demo/reset.

Part of the release gate (DATA 3.6). Never hard-code outcomes: if a scripted sale comes out ASK
with the trained model, investigate the features or generator, do not tune for the demo.
"""
import json
import sqlite3
from datetime import date

import pytest

from app.classifier.decide import decide
from app.config import DEMO_DATA_DIR, get_settings
from app.finance.summary import compute

SEED = DEMO_DATA_DIR / "seed.db"
pytestmark = pytest.mark.skipif(not SEED.exists(), reason="run python -m data.seed_demo first")
M001 = json.loads((DEMO_DATA_DIR / "M001_demo_day.json").read_text(encoding="utf-8"))
M002 = json.loads((DEMO_DATA_DIR / "M002_demo_day.json").read_text(encoding="utf-8"))
META = json.loads((DEMO_DATA_DIR / "seed_meta.json").read_text(encoding="utf-8")) if SEED.exists() else {}


@pytest.fixture
def demo(make_client, wall_clock):
    wall_clock("21:00:00")
    with make_client(DEMO_SEED_DB=str(SEED)) as c:
        r = c.post("/api/demo/reset", json={})
        assert r.status_code == 200, r.text
        assert r.json()["pending_demo_payments"] == {"M001": 15, "M002": 11}
        yield c


def totals(c, mid):
    s = c.get(f"/api/merchants/{mid}/summary").json()
    assert s["reconciliation_ok"]
    return (s["total_collections"]["amount_paise"], s["business_sales"]["amount_paise"],
            s["family_transfers"]["amount_paise"], s["pending"]["amount_paise"], s["pending"]["count"],
            s["expenses"]["amount_paise"], s["profit"]["amount_paise"])


def run_payments(c, script, upto, start=0):
    """Inject script items [start, upto) with /demo/next-payment and check each expected outcome."""
    results = []
    for item in script["payments"][start:upto]:
        r = c.post("/api/demo/next-payment", json={"merchant_id": script["merchant_id"]})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["transaction_id"] == item["request"]["transaction_id"]
        assert body["action"] == item["expected_action"], (item["demo_index"], body)
        assert body["suggested_classification"] == item["expected_suggested_classification"], (item["demo_index"], body)
        results.append(body)
    return results


def answer(c, script, ask):
    a = script["answer"]
    return c.post(f"/api/payments/{ask['transaction_id']}/confirm", json={
        "merchant_id": script["merchant_id"], "question_id": ask["question_id"],
        "confirmed_category": a["confirmed_category"], "channel": a["channel"],
        "utterance_text": a["utterance_text"], "remember_payer": a["remember_payer"],
    })


def db_conn():
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_m001_demo_day_rows_1_to_4(demo):
    #                      collections sales  family  pending n  expenses  profit
    assert demo.post("/api/expenses", json=M001["expense"]).status_code == 201
    assert totals(demo, "M001") == (0, 0, 0, 0, 0, 310000, -310000)               # row 1
    run_payments(demo, M001, 14)
    assert totals(demo, "M001") == (482000, 482000, 0, 0, 0, 310000, 172000)      # row 2
    (ask,) = run_payments(demo, M001, 15, start=14)
    assert ask["question_id"] and ask["classification"] == "PENDING"
    assert totals(demo, "M001") == (682000, 482000, 0, 200000, 1, 310000, 172000)  # row 3
    today = demo.get("/api/merchants/M001/questions", params={"date": "2026-11-15"}).json()["items"]
    assert [q["question_id"] for q in today] == [ask["question_id"]]
    assert len(demo.get("/api/merchants/M001/questions").json()["items"]) == 4  # + the 3 seeded ones
    r = answer(demo, M001, ask)
    assert r.status_code == 201 and r.json()["payer_memory"]["family_payer_configured"] is True
    assert totals(demo, "M001") == (682000, 482000, 200000, 0, 0, 310000, 172000)  # row 4


def _run_m001_with(demo, remember):
    script = json.loads(json.dumps(M001))
    script["answer"]["remember_payer"] = remember
    ask = run_payments(demo, script, 15)[14]
    assert answer(demo, script, ask).status_code == 201
    conn = db_conn()
    try:
        return decide(conn, merchant_id="M001", payer_id="P90001", payer_vpa_kind="PERSONAL", amount_paise=200000,
                      payment_type="P2P", timestamp="2026-11-15T20:30:00+05:30")
    finally:
        conn.close()


def test_after_remember_next_lakshmi_payment_is_merchant_config(demo):
    d = _run_m001_with(demo, remember=True)
    assert (d.suggested, d.action, d.source, d.confidence, d.confidence_kind) == (
        "FAMILY", "AUTO_CLASSIFY", "MERCHANT_CONFIG", None, "NONE")


def test_without_remember_next_lakshmi_payment_still_asks(demo):
    d = _run_m001_with(demo, remember=False)
    assert d.action == "ASK_MERCHANT" and d.suggested == "FAMILY"
    # Step 5 adds: confidence higher than the first time (payer memory), source PAYER_MEMORY.


def test_m002_demo_day(demo):
    assert demo.post("/api/expenses", json=M002["expense"]).status_code == 201
    ask = run_payments(demo, M002, 11)[10]
    assert answer(demo, M002, ask).status_code == 201
    assert totals(demo, "M002") == (785000, 635000, 150000, 0, 0, 420000, 215000)


def test_each_demo_payment_twice_counts_once(demo):
    for script in (M001, M002):
        for item in script["payments"]:
            assert demo.post("/api/payments", json=item["request"]).status_code == 201
            replay = demo.post("/api/payments", json=item["request"])
            assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
    assert totals(demo, "M001")[0] == 682000 and totals(demo, "M002")[0] == 785000


def test_notice_period_has_three_unresolved(demo):
    conn = db_conn()
    try:
        b = compute(conn, "M001", date(2026, 8, 1), date(2026, 10, 31))
    finally:
        conn.close()
    assert b.pending_count == 3 and b.reconciliation_ok
    notice = json.loads((DEMO_DATA_DIR / "notice_numbers.json").read_text(encoding="utf-8"))
    assert b.total_collections == notice["amount_questioned_paise"]  # difference vs notice = 0


def test_seed_ledger_verifies_after_reset(demo):
    for mid in ("M001", "M002", "M003"):
        assert demo.get(f"/api/merchants/{mid}/ledger/verify").json()["status"] == "VALID"


@pytest.mark.xfail(strict=True, reason="placeholder classifier until build step 5; remove this marker then")
def test_release_seed_was_built_with_the_trained_model():
    assert META["placeholder_classifier"] is False
