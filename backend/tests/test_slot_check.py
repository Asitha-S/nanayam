import pytest

import app.voice.answer as answer
from app.voice.answer import SlotCheckFailed, compose_answer


FACTS = {"sales": 482000, "expenses": 310000, "profit": 172000, "family": 200000, "pending_count": 0}


def test_compose_answer_uses_fixed_template_slots():
    text = compose_answer("profit_answer", FACTS, lang="ta")
    assert text.startswith("இன்னைக்கு கடை வியாபாரம்")
    assert "4,820 ரூபாய்" in text
    assert "3,100 ரூபாய்" in text
    assert "1,720 ரூபாய்" in text


def test_compose_answer_rejects_template_bug(monkeypatch):
    good = answer.templates("ta")
    monkeypatch.setattr(answer, "templates", lambda lang: {**good, "profit_answer": "இன்னைக்கு கடை வியாபாரம் {expenses}. செலவு {sales}. மீதம் {profit}."})
    with pytest.raises(SlotCheckFailed):
        compose_answer("profit_answer", FACTS, lang="ta")
