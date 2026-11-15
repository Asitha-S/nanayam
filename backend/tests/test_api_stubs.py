"""Every contract endpoint exists, returns its fixture, and uses the contract error shape."""
import json

import pytest

from app.config import FIXTURES_DIR


def fx(name):
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


GET_CASES = [
    ("/api/merchants", "merchants"),
    ("/api/merchants/M001", "merchant_M001"),
    ("/api/payments/TXN-M001-20261115-015", "payment_get_015"),
    ("/api/merchants/M001/payments", "payments_list_M001_2026-11-15"),
    ("/api/merchants/M001/questions", "questions_M001_open_all"),
    ("/api/merchants/M001/questions?date=2026-11-15", "questions_M001_open_2026-11-15"),
    ("/api/merchants/M001/expenses", "expenses_list_M001_2026-11-15"),
    ("/api/merchants/M001/ledger", "ledger_M001_2026-11-15"),
    ("/api/ledger/" + fx("ledger_entry_detail")["ledger_entry_id"], "ledger_entry_detail"),
    ("/api/merchants/M001/ledger/verify", "ledger_verify_valid"),
    ("/api/merchants/M001/learning", "learning_M001"),
    ("/api/evaluation", "evaluation"),
    ("/api/merchants/M001/tax-summary", "tax_summary_M001"),
    ("/api/merchants/M003/tax-summary", "tax_summary_M003"),
    ("/api/merchants/M001/notices/NTC-M001-001/evidence", "notice_evidence"),
    ("/api/merchants/M001/passport", "passport_M001"),
    ("/api/demo/script?merchant_id=M001", "demo_script_M001"),
]


@pytest.mark.parametrize("path, name", GET_CASES)
def test_get_returns_fixture(client, path, name):
    r = client.get(path)
    assert r.status_code == 200, r.text
    assert r.json() == fx(name)


def test_summary_sources(client):
    assert client.get("/api/merchants/M001/summary").json()["sources"] is None
    with_sources = client.get("/api/merchants/M001/summary?include_sources=true").json()
    assert with_sources == fx("summary_M001_after_confirm")


POST_CASES = [
    ("/api/payments", "payments_post_request_015", 201, "payments_post_015_ask"),
    ("/api/expenses", "expenses_post_request", 201, "expenses_post"),
    ("/api/payments/TXN-M001-20261115-015/confirm", "confirm_request_015", 201, "confirm_015"),
]


@pytest.mark.parametrize("path, request_fx, status, response_fx", POST_CASES)
def test_post_returns_fixture(client, wall_clock, path, request_fx, status, response_fx):
    wall_clock("12:00:00")
    r = client.post(path, json=fx(request_fx))
    assert r.status_code == status, r.text
    assert r.json() == fx(response_fx)


def test_other_posts(client):
    assert client.post("/api/demo/reset", json={}).json() == fx("demo_reset")
    assert client.post("/api/classify/preview", json={
        "merchant_id": "M001", "payer_id": "P90001", "amount_paise": 200000,
        "payment_type": "P2P", "timestamp": "2026-11-15T20:30:00+05:30",
    }).json() == fx("classify_preview_remembered")
    assert client.post("/api/expenses/EXP-M001-000318/void", json={"merchant_id": "M001", "reason": "Wrong amount"}).status_code == 201
    assert client.post("/api/payments/TXN-1/refund", json={
        "refund_id": "RF-M001-000012", "amount_paise": 6000, "timestamp": "2026-11-14T10:05:00+05:30", "reason": "x",
    }).status_code == 201
    assert client.post("/api/payments/TXN-1/reversal", json={"timestamp": "2026-11-14T12:00:00+05:30", "reason": "Bank reversal"}).status_code == 201
    assert client.put("/api/merchants/M001", json={"preferred_language": "ta"}).status_code == 200


def test_voice_stubs(client):
    body = {"merchant_id": "M001", "language": "ta", "voice_log_id": None, "open_question_id": None}
    assert client.post("/api/voice/interpret", json={**body, "text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen"}).json()["intent"] == "LOG_EXPENSE"
    assert client.post("/api/voice/interpret", json={**body, "text": "இன்னைக்கு எவ்வளவு லாபம்"}).json()["intent"] == "ASK_DAILY_PROFIT"
    assert client.post("/api/voice/interpret", json={**body, "text": "veettu panam", "open_question_id": "Q-M001-000213"}).json()["intent"] == "CONFIRM_TRANSACTION"
    assert client.post("/api/voice/answer", json={"merchant_id": "M001", "language": "ta", "intent": "ASK_DAILY_PROFIT", "date": "2026-11-15"}).json() == fx("voice_answer_profit")
    assert client.post("/api/voice/speak", json={"merchant_id": "M001", "language": "ta", "text": "சரி"}).json() == fx("voice_speak")
    live = client.post("/api/voice/transcribe", data={"language": "ta", "merchant_id": "M001"}, files={"audio": ("a.webm", b"bytes")})
    assert live.json()["recognition_mode"] == "LIVE"


def test_transcribe_demo_key_wrong_bytes_is_422(client):
    r = client.post(
        "/api/voice/transcribe",
        data={"language": "ta", "merchant_id": "M001", "demo_key": "ta/expense_koyambedu"},
        files={"audio": ("a.wav", b"not the clip")},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_exports(client):
    csv = client.get("/api/merchants/M001/export/csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    header = [line for line in csv.text.splitlines() if not line.startswith("#")][0]
    assert header.split(",")[0] == "ledger_entry_id" and header.split(",")[-1] == "hash"
    pdf = client.get("/api/merchants/M001/export/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


# --- health and demo tools ----------------------------------------------------
def test_health(client):
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok", "demo_mode": "cache_only", "demo_date": "2026-11-15", "db": "ok",
        "model_version": body["model_version"], "threshold": body["threshold"], "demo_tools": True, "tampered": False,
    }
    assert body["threshold"] >= 0.90


def test_health_threshold_is_effective_max(make_client):
    with make_client(CONF_THRESHOLD="0.97") as c:
        assert c.get("/api/health").json()["threshold"] >= 0.97


def test_tamper_flag_and_reset(client):
    client.post("/api/demo/tamper", json={"merchant_id": "M001", "ledger_entry_id": "LE-M001-004725"})
    assert client.get("/api/health").json()["tampered"] is True
    assert client.get("/api/merchants/M001/ledger/verify").json()["status"] == "TAMPERED"
    client.post("/api/demo/reset", json={})
    assert client.get("/api/health").json()["tampered"] is False


def test_next_payment_script(client):
    indexes = [client.post("/api/demo/next-payment", json={"merchant_id": "M001"}).json() for _ in range(15)]
    assert [p["demo_index"] for p in indexes] == list(range(1, 16))
    assert indexes[-1]["action"] == "ASK_MERCHANT" and indexes[-1]["demo_remaining"] == 0
    done = client.post("/api/demo/next-payment", json={"merchant_id": "M001"})
    assert done.status_code == 409 and done.json()["error"]["code"] == "INVALID_STATE"


@pytest.mark.parametrize("method, path", [
    ("post", "/api/demo/reset"), ("post", "/api/demo/next-payment"), ("get", "/api/demo/script?merchant_id=M001"), ("post", "/api/demo/tamper"),
])
def test_demo_tools_404_when_disabled(make_client, method, path):
    with make_client(ENABLE_DEMO_TOOLS="false") as c:
        r = getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert c.get("/api/health").json()["demo_tools"] is False


# --- errors -------------------------------------------------------------------
def test_unknown_merchant_404(client):
    r = client.get("/api/merchants/M999/summary")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_validation_error_shape(client):
    body = fx("payments_post_request_015")
    body["amount_paise"] = 0
    r = client.post("/api/payments", json=body)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and err["details"]["field"] == "amount_paise"


@pytest.mark.parametrize("field, value", [
    ("payment_type", "UPI"), ("amount_paise", 2000.5), ("amount_paise", "200000"), ("timestamp", "2026-11-15T19:42:10"),
])
def test_payment_validation(client, field, value):
    body = fx("payments_post_request_015")
    body[field] = value
    assert client.post("/api/payments", json=body).status_code == 422


def test_unknown_field_rejected(client):
    body = fx("payments_post_request_015") | {"surprise": 1}
    assert client.post("/api/payments", json=body).status_code == 422


def test_unknown_merchant_in_body_is_422(client):
    body = fx("payments_post_request_015") | {"merchant_id": "M999"}
    assert client.post("/api/payments", json=body).status_code == 422


def test_malformed_json_is_400(client):
    r = client.post("/api/payments", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_remember_payer_with_sale_is_422(client):
    body = fx("confirm_request_015") | {"confirmed_category": "SALE", "remember_payer": True}
    assert client.post("/api/payments/TXN-M001-20261115-015/confirm", json=body).status_code == 422


def test_question_mismatch_is_409(client):
    body = fx("confirm_request_015") | {"question_id": "Q-M001-000210"}
    r = client.post("/api/payments/TXN-M001-20261115-015/confirm", json=body)
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "QUESTION_MISMATCH"


@pytest.mark.parametrize("amount", [0, 99, 50_000_001])
def test_expense_amount_range(client, wall_clock, amount):
    wall_clock("12:00:00")
    body = fx("expenses_post_request") | {"amount_paise": amount}
    assert client.post("/api/expenses", json=body).status_code == 422


@pytest.mark.parametrize("timestamp", ["2026-11-15T23:00:00+05:30", "2026-11-07T05:40:00+05:30"])
def test_expense_time_window(client, wall_clock, timestamp):
    wall_clock("12:00:00")
    body = fx("expenses_post_request") | {"timestamp": timestamp}
    r = client.post("/api/expenses", json=body)
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "timestamp"


def test_unknown_audio_404(client):
    assert client.get("/api/audio/AUD-0000000000000000").status_code == 404
