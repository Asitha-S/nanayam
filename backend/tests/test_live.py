"""Live mode: payments that arrive on their own (POST /demo/live-payment), the customer /pay page's options and
rate limit, the Soundbox announcement, real speak/transcribe, LAN CORS, and scripted + live payments on one day."""
import json
from types import SimpleNamespace

import pytest

from app.config import FIXTURES_DIR
from conftest import run_m001_demo


def summary(c):
    return c.get("/api/merchants/M001/summary").json()


def assert_books_hold(c):
    s = summary(c)
    assert s["reconciliation_ok"] is True
    assert c.get("/api/merchants/M001/ledger/verify").json()["status"] == "VALID"
    return s


# ---- live payments ---------------------------------------------------------------------------------------------

def test_live_payment_goes_through_the_payments_path_at_the_current_time(real):
    r = real.post("/api/demo/live-payment", json={"merchant_id": "M001"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["transaction_id"].startswith("LIVE-M001-20261115-")
    assert p["timestamp"] == "2026-11-15T21:00:00+05:30"  # real time of day (wall clock 21:00), DEMO_DATE
    assert p["action"] in ("AUTO_CLASSIFY", "ASK_MERCHANT") and p["classification"] in ("SALE", "FAMILY", "PENDING")
    listed = real.get("/api/merchants/M001/payments").json()["items"]
    assert any(x["transaction_id"] == p["transaction_id"] for x in listed)
    entry = real.get(f"/api/ledger/{p['ledger_entry_id']}").json()
    assert entry["source_id"] == p["transaction_id"] and entry["entry_type"] == "PAYMENT_IN"
    assert_books_hold(real)


def test_many_live_payments_keep_the_books(real, wall_clock):
    kinds = set()
    for i in range(40):
        wall_clock(f"{10 + i // 6:02d}:{(i * 7) % 60:02d}:00")
        p = real.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json()
        kinds.add(p["action"])
        assert p["amount_paise"] >= 100
    s = assert_books_hold(real)
    assert real.get("/api/merchants/M001/payments").json()["count"] == 40
    assert s["total_collections"]["amount_paise"] > 0
    assert "AUTO_CLASSIFY" in kinds  # mostly confident sales


def test_pinned_demo_time_pins_live_payments_too(make_client, wall_clock):
    from app.config import DEMO_DATA_DIR

    wall_clock("10:00:00")
    with make_client(DEMO_SEED_DB=str(DEMO_DATA_DIR / "seed.db"), DEMO_TIME="21:30") as c:
        c.post("/api/demo/reset", json={})
        p = c.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json()
        assert p["timestamp"] == "2026-11-15T21:30:00+05:30"


def test_scripted_and_live_payments_coexist_on_one_day(real, wall_clock):
    wall_clock("09:00:00")
    live_before = [real.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json() for _ in range(5)]
    run_m001_demo(real)  # expense + the 15 scripted payments (times 06:12-19:42) + Lakshmi answered
    wall_clock("20:15:00")
    live_after = [real.post("/api/demo/live-payment", json={"merchant_id": "M001"}).json() for _ in range(5)]
    s = assert_books_hold(real)
    assert real.get("/api/merchants/M001/payments").json()["count"] == 25
    # the scripted day's figures are all still in there, and nothing was rejected as "future"
    assert s["business_sales"]["amount_paise"] >= 482000 and s["family_transfers"]["amount_paise"] >= 200000
    assert all(p["transaction_id"].startswith("LIVE-") for p in live_before + live_after)
    assert real.post("/api/demo/next-payment", json={"merchant_id": "M001"}).status_code == 409  # script finished


# ---- the customer /pay page --------------------------------------------------------------------------------------

def test_pay_options_list_people_without_hints(real):
    o = real.get("/api/demo/pay-options?merchant_id=M001").json()
    assert o["display_name"] == "Murugan Kaaikari Kadai"
    names = {p["payer_name"]: p for p in o["payers"]}
    assert names["Anbu Mess"]["role"] == "BUSINESS"
    assert names["Karthik"]["role"] == "PERSON" and names["Lakshmi R"]["role"] == "PERSON"
    assert sum(1 for p in o["payers"] if p["role"] == "CUSTOMER") >= 4
    for p in o["payers"]:  # the phone never sees how Naanayam would treat a payer
        assert set(p) == {"payer_id", "payer_name", "payer_vpa_kind", "role", "usual_payment_type"}


def _pay(c, txn, **extra):
    body = {"transaction_id": txn, "merchant_id": "M001", "payer_id": "P10411", "payer_name": "Senthil K",
            "payer_vpa_kind": "PERSONAL", "amount_paise": 5000, "payment_type": "P2M",
            "timestamp": c.get("/api/health").json()["now"], "description": None, **extra}
    return c.post("/api/payments", json=body, headers={"X-Naanayam-Client": "pay-page"})


def test_pay_page_one_payment_per_two_seconds(real):
    assert _pay(real, "PAY-T-1").status_code == 201
    r = _pay(real, "PAY-T-2")
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert r.json()["error"]["details"]["retry_after_s"] > 0
    # other clients (live mode, the laptop's own screens) are not limited
    assert real.post("/api/demo/live-payment", json={"merchant_id": "M001"}).status_code == 201


def test_new_customer_p2p_from_the_pay_page(real):
    r = _pay(real, "PAY-T-NEW", payer_id="PNEW123456", payer_name="Ganesh", amount_paise=200000, payment_type="P2P")
    assert r.status_code == 201
    assert r.json()["action"] in ("AUTO_CLASSIFY", "ASK_MERCHANT")
    assert_books_hold(real)


# ---- what the Soundbox says ------------------------------------------------------------------------------------

def test_announcement_tamil_telugu_english_and_question(real):
    first = real.post("/api/demo/next-payment", json={"merchant_id": "M001"}).json()  # ₹40, Senthil K
    a = real.get(f"/api/payments/{first['transaction_id']}/announcement?language=ta").json()
    assert a["text"] == "40 ரூபாய் வந்திருக்கு." and a["text_en"] == "Received 40 rupees." and a["question"] is None
    assert real.get(f"/api/payments/{first['transaction_id']}/announcement?language=te").json()["text"] == "40 రూపాయలు వచ్చాయి."
    for _ in range(14):
        last = real.post("/api/demo/next-payment", json={"merchant_id": "M001"}).json()
    a = real.get(f"/api/payments/{last['transaction_id']}/announcement?language=ta").json()
    assert a["text"] == "2,000 ரூபாய் வந்திருக்கு."
    q = real.get("/api/merchants/M001/questions?status=OPEN&date=2026-11-15").json()["items"][0]
    assert a["question"] == {"question_id": q["question_id"], "text": q["question_text"], "text_en": q["question_text_en"]}


def test_announcement_unknown_payment_is_404(real):
    assert real.get("/api/payments/NOPE/announcement").status_code == 404


# ---- speak / transcribe through the Sarvam client ---------------------------------------------------------------

def test_speak_uses_the_sarvam_client(real, monkeypatch):
    from app.routers import voice

    monkeypatch.setattr(voice.sarvam, "tts", lambda text, lang: SimpleNamespace(audio_id="AUD-x1", from_cache=True))
    r = real.post("/api/voice/speak", json={"merchant_id": "M001", "language": "ta", "text": "40 ரூபாய் வந்திருக்கு."})
    assert r.json() == {"audio_id": "AUD-x1", "audio_url": "/api/audio/AUD-x1", "from_cache": True}


def test_transcribe_uses_the_sarvam_client_and_logs(real, monkeypatch):
    from app.routers import voice

    monkeypatch.setattr(voice.sarvam, "stt", lambda data, lang, demo_key, filename: SimpleNamespace(
        text="auto-ku 200 rupees", recognition_mode="LIVE", from_cache=False, audio_sha256="ab" * 32))
    r = real.post("/api/voice/transcribe", data={"language": "ta", "merchant_id": "M001"}, files={"audio": ("a.webm", b"x" * 10)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "auto-ku 200 rupees" and body["recognition_mode"] == "LIVE" and body["voice_log_id"].startswith("VL-M001-")
    assert body != json.loads((FIXTURES_DIR / "voice_transcribe_live.json").read_text(encoding="utf-8"))


# ---- network ---------------------------------------------------------------------------------------------------

def test_network_lists_private_addresses_only(real):
    import ipaddress

    ips = real.get("/api/demo/network").json()["lan_ips"]
    assert isinstance(ips, list)
    assert all(ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback for ip in ips)


@pytest.mark.parametrize("origin,allowed", [
    ("http://localhost:5173", True), ("http://192.168.43.120:5173", True), ("http://10.0.0.7:5173", True),
    ("http://172.20.1.5:4173", True), ("http://evil.example.com", False), ("http://8.8.8.8:5173", False),
])
def test_cors_allows_the_lan_only(real, origin, allowed):
    r = real.options("/api/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert (r.headers.get("access-control-allow-origin") == origin) is allowed
