"""Endpoints still on fixtures return them; contract error shape and request validation.
Real P1 endpoints are covered in test_p1_flows.py."""
import json

import pytest

from app.config import FIXTURES_DIR


def fx(name):
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


GET_CASES = [
    ("/api/merchants/M001/notices/NTC-M001-001/evidence", "notice_evidence"),
]


@pytest.mark.parametrize("path, name", GET_CASES)
def test_get_returns_fixture(client, path, name):
    r = client.get(path)
    assert r.status_code == 200, r.text
    assert r.json() == fx(name)


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


@pytest.mark.parametrize("method, path", [
    ("post", "/api/demo/reset"), ("post", "/api/demo/next-payment"), ("get", "/api/demo/script?merchant_id=M001"), ("post", "/api/demo/tamper"),
])
def test_demo_tools_404_when_disabled(make_client, method, path):
    with make_client(ENABLE_DEMO_TOOLS="false") as c:
        r = getattr(c, method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
        assert c.get("/api/health").json()["demo_tools"] is False


# --- errors and validation (no database rows needed) ---------------------------
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
    r = client.post("/api/payments", json=body)
    assert r.status_code == 422 and r.json()["error"]["details"]["field"] == "merchant_id"


def test_malformed_json_is_400(client):
    r = client.post("/api/payments", content=b"{not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_remember_payer_with_sale_is_422(client):
    body = fx("confirm_request_015") | {"confirmed_category": "SALE", "remember_payer": True}
    assert client.post("/api/payments/TXN-M001-20261115-015/confirm", json=body).status_code == 422


@pytest.mark.parametrize("amount", [0, 99, 50_000_001])
def test_expense_amount_range(client, amount):
    body = fx("expenses_post_request") | {"amount_paise": amount}
    assert client.post("/api/expenses", json=body).status_code == 422


def test_unknown_audio_404(client):
    assert client.get("/api/audio/AUD-0000000000000000").status_code == 404


def test_evaluation_is_the_latest_run_file(client):
    from app.config import REPO_ROOT

    expected = json.loads((REPO_ROOT / "data" / "eval" / "latest.json").read_text(encoding="utf-8"))
    body = client.get("/api/evaluation").json()
    assert body == expected and body["data_label"].startswith("Synthetic data")
    for key in ("baseline", "with_feedback", "split", "pr_coverage_curve", "calibration", "label_mix", "conditions"):
        assert key in body
    assert set(body["conditions"]) == {"A", "B", "C", "D", "E"}
    assert set(body["conditions"]["E"]["family_recall_final"]) == {"count", "of", "rate"}
