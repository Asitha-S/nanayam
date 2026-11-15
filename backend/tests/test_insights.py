"""Merchants, learning, tax summary, passport and tamper on the committed seed (contract 1, 2, 7, 8, 9, 10)."""
import pytest

from app.config import DEMO_DATA_DIR

SEED = DEMO_DATA_DIR / "seed.db"
pytestmark = pytest.mark.skipif(not SEED.exists(), reason="run python -m data.seed_demo first")


@pytest.fixture
def demo(make_client, wall_clock):
    wall_clock("21:00:00")
    with make_client(DEMO_SEED_DB=str(SEED)) as c:
        assert c.post("/api/demo/reset", json={}).status_code == 200
        yield c


# --- merchants ------------------------------------------------------------------------------
def test_merchants_list_and_detail(demo):
    ms = demo.get("/api/merchants").json()["merchants"]
    assert [m["merchant_id"] for m in ms] == ["M001", "M002", "M003"]
    assert ms[0] == {"merchant_id": "M001", "display_name": "Murugan Kaaikari Kadai", "owner_name": "Murugan",
                     "business_category": "VEGETABLES", "preferred_language": "ta"}
    m = demo.get("/api/merchants/M001").json()
    assert m["city"] == "Chennai" and m["created_at"] == "2026-08-01T05:00:00+05:30"
    assert m["family_payers"] == [{"payer_id": "P90002", "payer_name": "Karthik", "relation_label": "Thambi (brother)"}]
    assert demo.get("/api/merchants/M999").status_code == 404


def test_put_merchant_partial_update(demo):
    r = demo.put("/api/merchants/M001", json={"family_payer_ids": ["P90002", "P90003"], "preferred_language": "te"})
    assert r.status_code == 200
    body = r.json()
    assert body["preferred_language"] == "te" and body["business_category"] == "VEGETABLES"
    assert [p["payer_id"] for p in body["family_payers"]] == ["P90002", "P90003"]
    removed = demo.put("/api/merchants/M001", json={"family_payer_ids": ["P90003"]}).json()
    assert [p["payer_id"] for p in removed["family_payers"]] == ["P90003"]
    unknown = demo.put("/api/merchants/M001", json={"family_payer_ids": ["P99999"]})
    assert unknown.status_code == 422 and unknown.json()["error"]["details"]["unknown"] == ["P99999"]
    assert demo.put("/api/merchants/M001", json={"business_category": "SHOES"}).status_code == 422
    # history is not rewritten
    first_karthik = demo.get("/api/merchants/M001/payments", params={"start_date": "2026-08-01", "end_date": "2026-08-01",
                                                                      "classification": "FAMILY"}).json()
    assert all(i["classification_source"] == "MERCHANT_CONFIG" for i in first_karthik["items"])


# --- learning ---------------------------------------------------------------------------------
def test_learning_activity_and_payers(demo):
    r = demo.get("/api/merchants/M001/learning").json()
    assert r["family_payers_configured"] == 1 and r["known_payers"] > 1000
    assert r["corrections_total"] >= r["payers_with_memory"] > 0
    assert set(r["questions_asked"]) == {"today", "last_7_days", "first_7_days"} and r["questions_asked"]["today"] == 0
    payers = {p["payer_name"]: p for p in r["payers"]}
    assert (payers["Karthik"]["kind"], payers["Karthik"]["source"]) == ("FAMILY_INSTRUCTION", "SETUP")
    assert payers["Selvi"]["kind"] == "MIXED" and (payers["Selvi"]["confirmed_family"], payers["Selvi"]["confirmed_sale"]) == (3, 2)
    assert len(r["recent_feedback"]) == 5 and "precision" not in str(r)  # /learning never returns precision


def test_learning_today_after_demo(demo):
    for _ in range(15):
        last = demo.post("/api/demo/next-payment", json={"merchant_id": "M001"}).json()
    demo.post(f"/api/payments/{last['transaction_id']}/confirm", json={
        "merchant_id": "M001", "question_id": last["question_id"], "confirmed_category": "FAMILY", "channel": "VOICE",
        "utterance_text": None, "remember_payer": True})
    r = demo.get("/api/merchants/M001/learning").json()
    assert r["questions_asked"]["today"] == 1 and r["auto_classified_today"] == 14
    assert r["family_payers_configured"] == 2
    assert r["recent_feedback"][0]["payer_name"] == "Lakshmi R" and r["recent_feedback"][0]["confirmed_category"] == "FAMILY"
    lakshmi = {p["payer_name"]: p for p in r["payers"]}["Lakshmi R"]
    assert (lakshmi["kind"], lakshmi["source"]) == ("FAMILY_INSTRUCTION", "CONFIRMATION")


# --- tax summary (DATA 8) ----------------------------------------------------------------------
def test_tax_summary_m001_exempt_likely(demo):
    t = demo.get("/api/merchants/M001/tax-summary").json()
    assert t["period"] == {"start_date": "2026-08-01", "end_date": "2026-11-15"}
    assert (t["gst_treatment"], t["ca_review_required"], t["flags"]) == ("EXEMPT_LIKELY", True, ["CA_REVIEW_REQUIRED"])
    assert "Not inferred from payments" in t["gst_treatment_basis"]
    s = demo.get("/api/merchants/M001/summary", params={"start_date": "2026-08-01", "end_date": "2026-11-15"}).json()
    assert t["business_sales"] == s["business_sales"] and t["total_collections"] == s["total_collections"]
    assert t["pending"]["count"] == 3 and t["expenses_recorded"]["count"] > 100


def test_tax_summary_m003_unknown_without_split(demo):
    t = demo.get("/api/merchants/M003/tax-summary").json()
    assert t["gst_treatment"] == "UNKNOWN" and t["flags"] == ["MIXED_CATEGORY_SPLIT_UNKNOWN", "CA_REVIEW_REQUIRED"]
    assert not any(k for k in t if "exempt" in k.lower() or "taxable" in k.lower() or "split" in k.lower())


# --- passport (DATA 10) ------------------------------------------------------------------------
def test_passport(demo):
    p = demo.get("/api/merchants/M001/passport").json()
    assert [m["month"] for m in p["months"]] == ["2026-08", "2026-09", "2026-10"]
    assert p["totals"]["raw_collections"]["amount_paise"] == sum(m["raw_collections_paise"] for m in p["months"])
    assert p["totals"]["recorded_business_income"]["amount_paise"] == sum(m["business_sales_paise"] for m in p["months"])
    assert p["share_of_collections_that_were_business_sales"] == round(
        p["totals"]["recorded_business_income"]["amount_paise"] / p["totals"]["raw_collections"]["amount_paise"], 3)
    oct_ = p["months"][2]
    assert oct_["unresolved_count"] == 3 and oct_["recorded_income_paise"] == oct_["business_sales_paise"]
    assert oct_["raw_collections_display"].startswith("₹")
    assert p["label"] == "Recorded business income summary. Not verified income. Not a credit decision."
    assert p["ledger_verify_status"] == "VALID" and "score" not in str(p).lower()
    assert len(demo.get("/api/merchants/M001/passport", params={"months": 1}).json()["months"]) == 1
    assert demo.get("/api/merchants/M001/passport", params={"months": 4}).status_code == 422


# --- tamper (contract 7) -----------------------------------------------------------------------
def test_tamper_detected_until_reset(demo):
    entry = demo.get("/api/merchants/M001/ledger", params={"start_date": "2026-10-01", "end_date": "2026-10-01",
                                                          "limit": 1}).json()["items"][0]["ledger_entry_id"]
    assert demo.post("/api/demo/tamper", json={"merchant_id": "M001", "ledger_entry_id": entry}).json() == {"tampered": True}
    v = demo.get("/api/merchants/M001/ledger/verify").json()
    assert (v["status"], v["first_invalid_entry_id"]) == ("TAMPERED", entry) and "hash_mismatch" in v["message"]
    assert demo.get("/api/health").json()["tampered"] is True
    assert demo.get("/api/merchants/M001/passport").json()["ledger_verify_status"] == "TAMPERED"
    demo.post("/api/demo/reset", json={})
    assert demo.get("/api/merchants/M001/ledger/verify").json()["status"] == "VALID"
    assert demo.get("/api/health").json()["tampered"] is False
    missing = demo.post("/api/demo/tamper", json={"merchant_id": "M001", "ledger_entry_id": "LE-M001-999999"})
    assert missing.status_code == 404
