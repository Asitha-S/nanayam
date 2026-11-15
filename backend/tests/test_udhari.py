"""Udhari, the credit book (contract section 13, flag UDHARI). A book beside the ledger: tab entries never touch the
ledger, a payment's classification or the summary."""
import uuid

import pytest

from app import clock

TAB_PAYERS = ["Bhuvana", "Pooja A", "Ramesh N", "Murali K"]  # oldest open tab first


@pytest.fixture
def udhari(make_client, wall_clock):
    """The committed demo seed after /demo/reset with UDHARI on. Wall clock 21:00."""
    from app.config import DEMO_DATA_DIR

    seed = DEMO_DATA_DIR / "seed.db"
    if not seed.exists():
        pytest.skip("run the release gate first")
    wall_clock("21:00:00")
    with make_client(DEMO_SEED_DB=str(seed), UDHARI="true") as c:
        assert c.post("/api/demo/reset", json={}).status_code == 200
        yield c


def crid() -> str:
    return str(uuid.uuid4())


def add(c, payer_id, rupees, request_id=None, **extra):
    return c.post(f"/api/tabs/{payer_id}/add", json={"client_request_id": request_id or crid(), "merchant_id": "M001",
                                                      "amount_paise": rupees * 100, "input_source": "MANUAL", **extra})


def settle(c, payer_id, txn, request_id=None):
    return c.post(f"/api/tabs/{payer_id}/settle", json={"client_request_id": request_id or crid(), "merchant_id": "M001",
                                                         "transaction_id": txn})


def pay(c, payer_id, name, rupees):
    """A payment through POST /payments at the backend's current time."""
    txn = f"TXN-M001-T-{uuid.uuid4().hex[:8]}"
    r = c.post("/api/payments", json={"transaction_id": txn, "merchant_id": "M001", "payer_id": payer_id, "payer_name": name,
                                      "payer_vpa_kind": "PERSONAL", "amount_paise": rupees * 100, "payment_type": "P2M",
                                      "timestamp": clock.iso(clock.now()), "description": None})
    assert r.status_code == 201, r.text
    return txn


def books(c):
    """What the ledger side says: summary figures and the verify status (must not move with tab entries)."""
    s = c.get("/api/merchants/M001/summary").json()
    keys = ("business_sales", "family_transfers", "expenses", "profit", "pending")
    return {k: s[k] for k in keys}, c.get("/api/merchants/M001/ledger/verify").json()["status"]


# ---- off by default ----------------------------------------------------------------------------------------------

def test_off_by_default_nothing_changes(real):
    assert real.get("/api/health").json()["features"] == {"udhari": False}
    assert real.get("/api/merchants/M001/tabs").status_code == 404
    assert add(real, "P10006", 300).status_code == 404
    assert settle(real, "P10006", "TXN-X").status_code == 404
    r = real.post("/api/voice/interpret", json={"merchant_id": "M001", "language": "ta", "text": "ரமேஷ் 300 கடன்"}).json()
    assert r["intent"] not in ("ADD_CREDIT", "ASK_DUES")
    live = real.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json()
    assert "tab_offer" not in real.get(f"/api/payments/{live['transaction_id']}/announcement").json()


# ---- the book -----------------------------------------------------------------------------------------------------

def test_seeded_tabs_oldest_first_with_their_sources(udhari):
    assert udhari.get("/api/health").json()["features"] == {"udhari": True}
    t = udhari.get("/api/merchants/M001/tabs").json()
    assert (t["total_due_display"], t["open_count"]) == ("₹4,810", 4)
    assert [i["payer_name"] for i in t["items"]] == TAB_PAYERS
    ramesh = next(i for i in t["items"] if i["payer_id"] == "P10006")
    assert ramesh["due_display"] == "₹2,300" and ramesh["opened_at"].startswith("2026-11-10")
    assert [e["balance_after_display"] for e in ramesh["entries"]] == ["₹1,500", "₹2,300"]
    assert {e["source"]["type"] for i in t["items"] for e in i["entries"]} == {"SEED"}
    assert t["offers"] == []
    assert t["spoken"]["language"] == "ta" and "4 பேர்" in t["spoken"]["text"] and "4,810" in t["spoken"]["text"]
    te = udhari.get("/api/merchants/M001/tabs?language=te").json()["spoken"]
    assert te["language"] == "te" and "4 మంది" in te["text"]


def test_reset_keeps_one_copy_of_the_seed(udhari):
    assert udhari.post("/api/demo/reset", json={}).status_code == 200
    assert udhari.get("/api/merchants/M001/tabs").json()["total_due_display"] == "₹4,810"


def test_add_is_idempotent_and_never_touches_the_books(udhari):
    before = books(udhari)
    key = crid()
    r = add(udhari, "P10006", 300, key, input_source="VOICE", language="ta", utterance_text="ரமேஷ் 300 கடன்")
    assert r.status_code == 201
    assert (r.json()["kind"], r.json()["amount_display"], r.json()["due_display"]) == ("ADD", "₹300", "₹2,600")
    again = add(udhari, "P10006", 300, key, input_source="VOICE", language="ta", utterance_text="ரமேஷ் 300 கடன்")
    assert again.status_code == 200 and again.json()["idempotent_replay"] is True
    assert again.json()["tab_entry_id"] == r.json()["tab_entry_id"]
    conflict = add(udhari, "P10006", 400, key, input_source="VOICE", language="ta", utterance_text="ரமேஷ் 300 கடன்")
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "DUPLICATE_CONFLICT"
    assert add(udhari, "P99999", 300).status_code == 404
    assert add(udhari, "P10006", 0).status_code == 422
    assert books(udhari) == before
    entry = udhari.get("/api/merchants/M001/tabs").json()["items"][2]["entries"][-1]
    assert entry["source"] == {"type": "VOICE", "transaction_id": None, "ledger_entry_id": None,
                               "utterance_text": "ரமேஷ் 300 கடன்", "voice_log_id": None}


def test_live_payment_offers_and_settles_part_of_the_tab(udhari):
    live = udhari.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json()
    assert (live["payer_name"], live["amount_display"]) == ("Ramesh N", "₹2,000")
    txn = live["transaction_id"]
    offer = udhari.get(f"/api/payments/{txn}/announcement").json()["tab_offer"]
    assert (offer["payer_name"], offer["payment_display"], offer["due_display"], offer["settle_display"]) == \
        ("Ramesh N", "₹2,000", "₹2,300", "₹2,000")
    assert "கழிக்கவா" in offer["text"] and offer["text_en"] == "Ramesh N paid 2,000 rupees. Take it off the tab? 2,300 rupees due."
    listed = udhari.get("/api/merchants/M001/tabs").json()["offers"]
    assert [o["transaction_id"] for o in listed] == [txn] and listed[0]["ledger_entry_id"]

    before = books(udhari)
    key = crid()
    r = settle(udhari, "P10006", txn, key)
    assert r.status_code == 201
    body = r.json()
    assert (body["amount_display"], body["due_before_display"], body["due_display"], body["payment_amount_display"]) == \
        ("₹2,000", "₹2,300", "₹300", "₹2,000")
    assert books(udhari) == before  # the payment stays a sale; the ledger and summary don't move
    replay = settle(udhari, "P10006", txn, key)
    assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
    assert replay.json()["due_before_display"] == "₹2,300" and replay.json()["amount_display"] == "₹2,000"
    twice = settle(udhari, "P10006", txn)
    assert twice.status_code == 409 and twice.json()["error"]["details"]["reason"] == "PAYMENT_ALREADY_USED"
    assert udhari.get(f"/api/payments/{txn}/announcement").json()["tab_offer"] is None
    t = udhari.get("/api/merchants/M001/tabs").json()
    assert t["offers"] == [] and t["total_due_display"] == "₹2,810"
    last = next(i for i in t["items"] if i["payer_id"] == "P10006")["entries"][-1]
    assert last["kind"] == "SETTLE" and last["source"]["type"] == "PAYMENT" and last["source"]["transaction_id"] == txn
    assert last["source"]["ledger_entry_id"] == listed[0]["ledger_entry_id"]
    nxt = udhari.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json()
    assert nxt["transaction_id"] != txn and not (nxt["payer_name"] == "Ramesh N" and nxt["amount_display"] == "₹2,000")


def test_settle_takes_at_most_what_is_due(udhari):
    txn = pay(udhari, "P10005", "Murali K", 1000)
    r = settle(udhari, "P10005", txn).json()
    assert (r["amount_display"], r["due_display"]) == ("₹460", "₹0")
    other = pay(udhari, "P10005", "Murali K", 50)
    nothing = settle(udhari, "P10005", other)
    assert nothing.status_code == 409 and nothing.json()["error"]["details"]["reason"] == "NOTHING_DUE"
    t = udhari.get("/api/merchants/M001/tabs").json()
    assert t["open_count"] == 3 and t["items"][-1]["payer_name"] == "Murali K"  # settled tabs go last
    assert udhari.get(f"/api/payments/{other}/announcement").json()["tab_offer"] is None


def test_settle_rejects_someone_elses_payment(udhari):
    txn = pay(udhari, "P10001", "Bhuvana", 500)
    r = settle(udhari, "P10006", txn)
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert settle(udhari, "P10006", "TXN-NOPE").status_code == 404


def test_fifo_opened_at_moves_to_the_oldest_unpaid_add(udhari):
    txn = pay(udhari, "P10006", "Ramesh N", 1500)  # pays off the 10 Nov ₹1,500 exactly
    settle(udhari, "P10006", txn)
    ramesh = next(i for i in udhari.get("/api/merchants/M001/tabs").json()["items"] if i["payer_id"] == "P10006")
    assert ramesh["due_display"] == "₹800" and ramesh["opened_at"].startswith("2026-11-13")


# ---- voice --------------------------------------------------------------------------------------------------------

def say(c, text, language="ta"):
    r = c.post("/api/voice/interpret", json={"merchant_id": "M001", "language": language, "text": text})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("text", ["ரமேஷ் 300 கடன்", "Ramesh 300 udhari", "ரமேஷுக்கு 300 கடன் குடுத்தேன்",
                                  "ரமேஷ் கணக்குல 300 எழுது"])
def test_add_credit_finds_the_payer(udhari, text):
    r = say(udhari, text)
    e = r["entities"]
    assert r["intent"] == "ADD_CREDIT" and not r["needs_clarification"]
    assert (e["payer_id"], e["payer_name"], e["amount_paise"], e["amount_display"]) == ("P10006", "Ramesh N", 30000, "₹300")
    assert e["payer_candidates"][0] == {"payer_id": "P10006", "payer_name": "Ramesh N"}
    assert r["confirmation_text"].startswith("Ramesh N கணக்குல 300") and r["confirmation_text"].endswith("கடன் எழுதவா?")


def test_add_credit_asks_for_what_is_missing(udhari):
    no_name = say(udhari, "கடன் 400")
    assert no_name["intent"] == "ADD_CREDIT" and no_name["needs_clarification"]
    assert no_name["clarification_text"] == "யார் கணக்குல எழுதணும்? பேர் சொல்லுங்க."
    no_amount = say(udhari, "ரமேஷ் கடன்")
    assert no_amount["intent"] == "ADD_CREDIT" and no_amount["needs_clarification"]
    assert no_amount["entities"]["amount_paise"] is None and no_amount["entities"]["payer_id"] == "P10006"
    unknown = say(udhari, "Zubair 250 udhari")
    assert unknown["entities"]["payer_id"] is None and len(unknown["entities"]["payer_candidates"]) == 6
    assert unknown["confirmation_text"].startswith("Zubair கணக்குல")
    te = say(udhari, "రమేష్ 300 అప్పు", "te")
    assert te["intent"] == "ADD_CREDIT" and te["confirmation_text"].endswith("అప్పు రాయనా?")


@pytest.mark.parametrize("text", ["யாரெல்லாம் பணம் தரணும்?", "who owes me", "baaki evlo?", "யார் யார் கடன் வச்சிருக்காங்க?"])
def test_ask_dues(udhari, text):
    r = say(udhari, text)
    assert r["intent"] == "ASK_DUES" and r["entities"] == {"date": "2026-11-15"}


def test_everyday_sentences_read_the_same_with_udhari_on(udhari):
    assert say(udhari, "வீடுல இன்னும் ₹6000 செலவானது.")["intent"] == "LOG_EXPENSE"
    assert say(udhari, "இன்னைக்கு எவ்வளவு லாபம்?")["intent"] == "ASK_DAILY_PROFIT"
    assert say(udhari, "auto-ku 200 rupees")["entities"]["category"] == "TRANSPORT"
