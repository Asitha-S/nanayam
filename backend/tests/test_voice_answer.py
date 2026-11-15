"""POST /voice/answer: fixed templates, positional slot check, TTS (VOICE_AND_NOTICE 6, contract 6)."""
import base64
from types import SimpleNamespace

import httpx
import pytest

from app.voice import answer as voice_answer
from conftest import run_m001_demo

pytestmark = pytest.mark.timeout(900)
BODY = {"merchant_id": "M001", "language": "ta", "intent": "ASK_DAILY_PROFIT", "date": "2026-11-15"}


def test_evening_answer_matches_contract_text_and_summary(real):
    run_m001_demo(real)
    r = real.post("/api/voice/answer", json=BODY)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["text"] == ("இன்னைக்கு கடை வியாபாரம் 4,820 ரூபாய். செலவு 3,100 ரூபாய். மீதம் 1,720 ரூபாய். "
                         "வீட்டு பணம் 2,000 ரூபாய் இதுல சேர்க்கல.")  # contract 6 example, exactly
    s = real.get("/api/merchants/M001/summary").json()
    assert a["facts"]["business_sales"] == s["business_sales"] and a["facts"]["profit"] == {
        "amount_paise": 172000, "amount_display": "₹1,720"}
    assert a["number_check"] == {"passed": True, "slots": {"sales": 482000, "expenses": 310000, "profit": 172000,
                                                           "family": 200000}}  # only spoken slots, as contract 6
    assert a["scope_note"].startswith("UPI payments only")
    assert a["audio_id"] is None and a["audio_error"] == "CACHE_MISS"  # cache_only, nothing cached: text only


def test_morning_loss_and_pending_wording(real):
    real.post("/api/expenses", json=__import__("json").loads(
        (__import__("app.config", fromlist=["DEMO_DATA_DIR"]).DEMO_DATA_DIR / "M001_demo_day.json")
        .read_text(encoding="utf-8"))["expense"])
    morning = real.post("/api/voice/answer", json=BODY).json()
    assert morning["text"] == "இன்னைக்கு கடை வியாபாரம் 0 ரூபாய். செலவு 3,100 ரூபாய். இதுவரைக்கும் நஷ்டம் 3,100 ரூபாய்."
    assert morning["number_check"]["slots"]["loss"] == 310000
    for _ in range(15):
        real.post("/api/demo/next-payment", json={"merchant_id": "M001"})
    pending = real.post("/api/voice/answer", json=BODY).json()
    assert pending["text"].endswith("இன்னும் 1 பணம் கடையா வீடா-ன்னு சொல்லல.")  # says how many are unconfirmed
    assert pending["facts"]["pending_count"] == 1


def test_other_languages_dates_and_intents_are_rejected(real):
    assert real.post("/api/voice/answer", json=BODY | {"language": "te"}).status_code == 422  # no te.json yet
    assert real.post("/api/voice/answer", json=BODY | {"date": "2026-11-14"}).status_code == 422
    assert real.post("/api/voice/answer", json=BODY | {"intent": "LOG_EXPENSE"}).status_code == 422
    assert real.post("/api/voice/answer", json=BODY | {"merchant_id": "M999"}).status_code == 422


FACTS = {"business_sales": 482000, "expenses": 310000, "profit": 172000, "family_transfers": 200000, "pending_count": 0}


@pytest.mark.parametrize("broken", [
    "இன்னைக்கு கடை வியாபாரம் {expenses}. செலவு {sales}. மீதம் {profit}.",   # swapped slots, same numbers
    "இன்னைக்கு கடை வியாபாரம் {sales}. செலவு {expenses}.",                  # a slot missing
    "இன்னைக்கு கடை வியாபாரம் {sales}. செலவு {expenses}. மீதம் 1,720 ரூபாய்.",  # a number typed into the template
    "இன்னைக்கு {sales}. {expenses}. {profit}. {tax}.",                      # unknown slot
])
def test_slot_check_catches_template_bugs(monkeypatch, broken):
    good = voice_answer.templates("ta")
    monkeypatch.setattr(voice_answer, "templates", lambda lang: {**good, "profit_answer": broken})
    with pytest.raises(voice_answer.SlotCheckFailed):
        voice_answer.compose(FACTS, "ta")


@pytest.mark.parametrize("figure", voice_answer.FIGURES)
@pytest.mark.parametrize("how", ["none", "absent"])
def test_missing_figure_is_a_500_and_never_spoken(real, monkeypatch, figure, how):
    facts = dict(FACTS)
    if how == "none":
        facts[figure] = None
    else:
        del facts[figure]
    monkeypatch.setattr(voice_answer, "compute", lambda *a: SimpleNamespace(**facts))
    called = []
    monkeypatch.setattr(voice_answer.sarvam, "tts", lambda *a: called.append(a))
    r = real.post("/api/voice/answer", json=BODY)
    assert r.status_code == 500, r.text
    error = r.json()["error"]
    assert error["code"] == "INTERNAL_ERROR" and figure in error["message"]
    assert not called  # never spoken, not even a partial answer


def test_template_bug_is_a_500_and_never_spoken(real, monkeypatch):
    run_m001_demo(real)
    good = voice_answer.templates("ta")
    monkeypatch.setattr(voice_answer, "templates",
                        lambda lang: {**good, "profit_answer": "இன்னைக்கு கடை வியாபாரம் {expenses}. செலவு {sales}. மீதம் {profit}."})
    called = []
    monkeypatch.setattr(voice_answer.sarvam, "tts", lambda *a: called.append(a))
    r = real.post("/api/voice/answer", json=BODY)
    assert r.status_code == 500 and "Slot check failed" in r.json()["error"]["message"] and not called


def test_answer_is_spoken_through_the_sarvam_client(real, env, monkeypatch):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k", DEMO_SEED_DB=str(
        __import__("app.config", fromlist=["DEMO_DATA_DIR"]).DEMO_DATA_DIR / "seed.db"))
    sent = []

    def fake_send(method, url, *, timeout, headers=None, json=None, **kw):
        sent.append(json)
        return httpx.Response(200, json={"audios": [base64.b64encode(b"RIFFwav").decode()]},
                              request=httpx.Request(method, url))

    monkeypatch.setattr(voice_answer.sarvam, "_send", fake_send)
    run_m001_demo(real)
    a = real.post("/api/voice/answer", json=BODY).json()
    assert a["audio_id"].startswith("AUD-") and a["audio_error"] is None
    assert sent[0]["text"] == a["text"]  # exactly the slot-checked text is spoken
    assert real.get(f"/api/audio/{a['audio_id']}").content == b"RIFFwav"
