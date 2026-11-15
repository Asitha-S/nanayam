"""POST /voice/interpret reads the actual text (VOICE_AND_NOTICE 5.2-5.4, contract 6). Never a fixture."""
import json

import pytest

from app.config import FIXTURES_DIR
from app.voice import rules

BODY = {"merchant_id": "M001", "language": "ta", "voice_log_id": None, "open_question_id": None}


def say(client, text, **extra):
    r = client.post("/api/voice/interpret", json={**BODY, "text": text, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---- the seven required cases ------------------------------------------------------------------------------

def test_koyambedu_expense(real):
    r = say(real, "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen")
    assert r["intent"] == "LOG_EXPENSE" and not r["needs_clarification"]
    e = r["entities"]
    assert (e["amount_paise"], e["amount_display"], e["category"]) == (310000, "₹3,100", "STOCK_PURCHASE")
    assert e["date"] == "2026-11-15" and "Kaaikari" in e["description"] and "Koyambedu" in e["description"]
    assert r["confirmation_text"] == "3,100 ரூபாய் சரக்கு செலவு (Koyambedu, Kaaikari). சரியா?"
    assert r["validation"] == {"amount_found_in_text": True, "category_valid": True}
    assert r["interpreter"] == "RULES" and r["from_cache"] is False  # tests run cache_only: no LLM answer


def test_auto_fare(real):
    r = say(real, "auto-ku 200 rupees")
    assert r["intent"] == "LOG_EXPENSE"
    assert (r["entities"]["amount_paise"], r["entities"]["category"]) == (20000, "TRANSPORT")


def test_tamil_fraction_words(real):
    r = say(real, "ஒண்ணரை ஆயிரம் சரக்கு வாங்கினேன்")
    assert r["intent"] == "LOG_EXPENSE"
    assert (r["entities"]["amount_paise"], r["entities"]["amount_display"]) == (150000, "₹1,500")
    assert r["entities"]["category"] == "STOCK_PURCHASE"


def test_profit_question(real):
    r = say(real, "இன்னைக்கு எவ்வளவு லாபம்")
    assert r["intent"] == "ASK_DAILY_PROFIT" and r["entities"] == {"date": "2026-11-15"}
    assert not r["needs_clarification"]


def test_family_answer_with_open_question(real):
    q = real.get("/api/merchants/M001/questions?status=OPEN").json()["items"][0]
    r = say(real, "வீட்டு பணம்", open_question_id=q["question_id"])
    assert r["intent"] == "CONFIRM_TRANSACTION"
    assert r["entities"] == {"confirmed_category": "FAMILY", "remember_payer": False}


def test_no_amount_needs_clarification(real):
    r = say(real, "kaaikari vaanginen")
    assert r["intent"] == "LOG_EXPENSE" and r["needs_clarification"] is True
    assert r["entities"]["amount_paise"] is None and r["confirmation_text"] is None
    assert r["clarification_text"] == "எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க."
    assert r["validation"]["amount_found_in_text"] is False


def test_nonsense_is_unknown(real):
    r = say(real, "blue elephant dancing")
    assert r["intent"] == "UNKNOWN" and r["needs_clarification"] is True and r["entities"] == {}
    assert r["clarification_text"].startswith("புரியல")


# ---- never a canned response -------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["voice_interpret_expense", "voice_interpret_profit", "voice_interpret_confirm"])
def test_no_fixture_comes_back(real, name):
    canned = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    for text in ("blue elephant dancing", "auto-ku 200 rupees", "ஒண்ணரை ஆயிரம் சரக்கு வாங்கினேன்"):
        assert say(real, text) != canned


# ---- more of the rules ---------------------------------------------------------------------------------------

def test_confirm_without_open_question_is_unknown(real):
    assert say(real, "வீட்டு பணம்")["intent"] == "UNKNOWN"
    assert say(real, "வீட்டு பணம்", open_question_id="Q-M001-999999")["intent"] == "UNKNOWN"  # no such question


def test_remember_prompt_answer_keeps_the_answer_and_remembers(real):
    q = real.get("/api/merchants/M001/questions?status=OPEN").json()["items"][0]
    real.post(f"/api/payments/{q['transaction_id']}/confirm", json={
        "merchant_id": "M001", "question_id": q["question_id"], "confirmed_category": "FAMILY", "channel": "TAP",
        "utterance_text": None, "remember_payer": False})
    r = say(real, "ஆமா, எப்பவும்", open_question_id=q["question_id"])
    assert r["intent"] == "CONFIRM_TRANSACTION"
    assert r["entities"] == {"confirmed_category": "FAMILY", "remember_payer": True}


def test_both_sale_and_family_words_ask_again(real):
    q = real.get("/api/merchants/M001/questions?status=OPEN").json()["items"][0]
    r = say(real, "கடை இல்ல வீட்டு பணம்", open_question_id=q["question_id"])
    assert r["intent"] == "CONFIRM_TRANSACTION" and r["needs_clarification"] is True
    assert r["clarification_text"] == "கடை வியாபாரமா, வீட்டு பணமா? கீழ தட்டுங்க."


def test_telugu_expense_and_template(real):
    r = say(real, "కూరగాయలు 500 రూపాయలు కొన్నాను", language="te", merchant_id="M002")
    assert r["intent"] == "LOG_EXPENSE" and r["entities"]["amount_paise"] == 50000
    assert r["entities"]["category"] == "STOCK_PURCHASE"
    assert r["confirmation_text"].endswith("సరేనా?") and "500 రూపాయలు" in r["confirmation_text"]


def test_yesterday_profit(real):
    assert say(real, "nethu evvalavu labham")["entities"] == {"date": "2026-11-14"}


def test_out_of_range_amount_asks_again(real):
    r = say(real, "10,00,000 sarakku vaangi")
    assert r["intent"] == "LOG_EXPENSE" and r["needs_clarification"] is True and r["entities"]["amount_paise"] is None


def test_article_one_is_not_the_amount(real):
    r = say(real, "ஒரு ஆட்டோ-க்கு 200 ரூபாய் செலவு")
    assert r["entities"]["amount_paise"] == 20000 and r["entities"]["category"] == "TRANSPORT"


# ---- the LLM path: only for sentences the rules can't read --------------------------------------------------
SENT = "Lakshmi-ku 500 anuppunen"  # "I sent Lakshmi 500": money words the rules leave alone (UNKNOWN)


def _llm_says(monkeypatch, **out):
    from app.voice import interpret as llm

    base = {"intent": None, "amount_rupees": None, "amount_text_span": None, "category": None, "description": None,
            "day": "today", "confirmed_category": None, "remember_payer": False, "status": "SUCCESS"}
    monkeypatch.setattr(llm, "interpret_utterance", lambda text, **kw: {**base, **out})


def test_rules_read_first_and_the_llm_is_not_asked(real, monkeypatch):
    def never(text, **kw):
        raise AssertionError("the LLM was asked about a sentence the rules read")

    from app.voice import interpret as llm
    monkeypatch.setattr(llm, "interpret_utterance", never)
    r = say(real, "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen")
    assert r["interpreter"] == "RULES" and r["entities"]["amount_paise"] == 310000


def test_llm_answer_is_used_when_the_rules_cant_read_it(real, monkeypatch):
    assert say(real, SENT)["intent"] == "UNKNOWN"  # the rules alone
    _llm_says(monkeypatch, intent="LOG_EXPENSE", amount_rupees=500, amount_text_span="500", category="OTHER",
              description="Lakshmi")
    r = say(real, SENT)
    assert r["interpreter"] == "LLM" and r["entities"]["amount_paise"] == 50000 and r["entities"]["description"] == "Lakshmi"


def test_llm_amount_not_in_the_text_is_not_trusted(real, monkeypatch):
    _llm_says(monkeypatch, intent="LOG_EXPENSE", amount_rupees=9999, amount_text_span="9,999", category="OTHER")
    r = say(real, SENT)
    assert r["interpreter"] == "LLM" and r["needs_clarification"] is True and r["entities"]["amount_paise"] is None


def test_llm_profit_with_a_sum_and_no_profit_word_is_not_trusted(real, monkeypatch):
    _llm_says(monkeypatch, intent="ASK_DAILY_PROFIT")
    r = say(real, SENT)
    assert r["intent"] == "UNKNOWN" and r["interpreter"] == "RULES"
    r = say(real, "business eppadi irukku")  # no figure: the LLM's profit reading stands
    assert r["intent"] == "ASK_DAILY_PROFIT" and r["interpreter"] == "LLM"


def test_llm_failure_falls_back_to_rules(real, monkeypatch):
    from app.voice import interpret as llm

    def boom(text, **kw):
        raise RuntimeError("Sarvam down")

    monkeypatch.setattr(llm, "interpret_utterance", boom)
    r = say(real, SENT)
    assert r["interpreter"] == "RULES" and r["intent"] == "UNKNOWN"


def test_slow_llm_never_holds_the_answer(real, monkeypatch):
    import time

    from app.voice import interpret as llm
    from app.voice import interpreter

    monkeypatch.setattr(interpreter, "LLM_BUDGET_S", 0.3)

    def slow(text, **kw):
        time.sleep(1.5)
        return {"intent": "ASK_DAILY_PROFIT", "status": "SUCCESS"}

    monkeypatch.setattr(llm, "interpret_utterance", slow)
    t0 = time.monotonic()
    r = say(real, "hello there")
    assert time.monotonic() - t0 < 1.2
    assert r["intent"] == "UNKNOWN" and r["interpreter"] == "RULES"


# ---- parse_amount forms (VOICE_AND_NOTICE 5.2) --------------------------------------------------------------

@pytest.mark.parametrize("span,rupees", [
    ("3,100", 3100), ("3100", 3100), ("3 100", 3100), ("1,50,000", 150000), ("3k", 3000), ("2.5k", 2500),
    ("three thousand one hundred", 3100), ("two lakh fifty thousand", 250000), ("five hundred", 500),
    ("ஒண்ணரை ஆயிரம்", 1500), ("ரெண்டரை ஆயிரம்", 2500), ("அரை லட்சம்", 50000), ("கால் லட்சம்", 25000),
    ("முக்கால் லட்சம்", 75000), ("மூவாயிரத்து நூறு", 3100), ("ஆயிரத்து ஐநூறு", 1500), ("இருநூறு", 200),
    ("நூத்தி ஐம்பது", 150), ("தொள்ளாயிரம்", 900), ("ரெண்டாயிரத்து ஐநூறு", 2500), ("ஐம்பது", 50),
    ("రెండు వేల ఐదు వందలు", 2500), ("నూట యాభై", 150), ("ఒకటిన్నర వేలు", 1500), ("రెండున్నర వేలు", 2500),
    ("లక్ష", 100000), ("aayiram", 1000), ("rendu aayirathu anju nooru", 2500), ("onnarai aayiram", 1500),
    ("veyyi", 1000), ("vanda", 100),
])
def test_parse_amount(span, rupees):
    assert rules.parse_amount(span) == rupees


@pytest.mark.parametrize("span", ["kaaikari", "", "அரை", "1.5"])
def test_parse_amount_rejects(span):
    with pytest.raises(ValueError):
        rules.parse_amount(span)
