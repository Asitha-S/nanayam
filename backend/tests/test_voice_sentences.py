"""The rule interpreter on everyday sentences: Tamil, Tanglish, Telugu, English. Every expense still goes to a
confirmation card (nothing is saved until the merchant says yes), so the rules read generously: a rupee figure that is
not a profit question and not money coming in is proposed as an expense."""
from datetime import date

import pytest

from app.voice import rules

TODAY = date(2026, 11, 15)
E, P, U = "LOG_EXPENSE", "ASK_DAILY_PROFIT", "UNKNOWN"
ST, TR, PK, RE, WA, UT, OT = "STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT", "WAGES", "UTILITIES", "OTHER"

EXPENSES = [
    # Tamil script
    ("வீடுல இன்னும் ₹6000 செலவானது.", 6000, OT),
    ("கோயம்பேடுல 3100 ரூபாய்க்கு காய்கறி வாங்கினேன்", 3100, ST),
    ("ஆட்டோக்கு 200 ரூபாய் கொடுத்தேன்", 200, TR),
    ("கடை வாடகை 8000 கட்டினேன்", 8000, RE),
    ("பையனுக்கு சம்பளம் 3000 கொடுத்தேன்", 3000, WA),
    ("கரண்ட் பில் 1200 கட்டினேன்", 1200, UT),
    ("கவர் வாங்க 150 ரூபாய் ஆச்சு", 150, PK),
    ("பெட்ரோல் 500 போட்டேன்", 500, TR),
    ("இன்னைக்கு தக்காளி 2500 ரூபாய்க்கு வாங்கினேன்", 2500, ST),
    ("மூவாயிரம் ரூபாய் சரக்கு வாங்கினேன்", 3000, ST),
    ("ஒண்ணரை ஆயிரம் கூலி கொடுத்தேன்", 1500, WA),
    ("தண்ணி கேன் 60 ரூபாய்", 60, UT),
    ("500 ரூபாய் செலவு", 500, OT),
    ("2000 ரூபாய் கொடுத்தேன்", 2000, OT),
    ("டீ செலவு 80", 80, OT),
    ("வெங்காயம் 1800க்கு வாங்கினேன்", 1800, ST),
    ("6000 செலவாச்சு", 6000, OT),
    ("500 ரூபாய் செலவழிச்சேன்", 500, OT),
    ("500 selavaachu", 500, OT),
    # Tanglish
    ("Koyambedu-la 3,100 rupees-ku kaaikari vaanginen", 3100, ST),
    ("auto-ku 200 rupees", 200, TR),
    ("rent 8000 kattinen", 8000, RE),
    ("petrol 500 potten", 500, TR),
    ("paiyanukku sambalam 3000 kuduthen", 3000, WA),
    ("current bill 1200 kattinen", 1200, UT),
    ("cover 150 rupees vaangunen", 150, PK),
    ("veetu selavu 6000", 6000, OT),
    # English
    ("spent 450 on tea", 450, OT),
    ("paid 2k for transport", 2000, TR),
    ("bought vegetables for 3100", 3100, ST),
    ("shop rent 8000", 8000, RE),
    ("gave 1500 salary to the helper", 1500, WA),
    # Telugu
    ("ఆటోకి 300 ఖర్చైంది", 300, TR),
    ("4,200 రూపాయలకు పండ్లు కొన్నాను", 4200, ST),
    ("అద్దె 8000 కట్టాను", 8000, RE),
    ("కూలి 1500 ఇచ్చాను", 1500, WA),
    ("కరెంట్ బిల్లు 1200 కట్టాను", 1200, UT),
    ("ఇంట్లో 5000 ఖర్చు అయింది", 5000, OT),
]

PROFIT = [
    "இன்னைக்கு எவ்வளவு லாபம்?",
    "இன்னைக்கு எவ்வளவு சம்பாதிச்சேன்?",
    "இன்னைக்கு கணக்கு சொல்லு",
    "இன்னைக்கு வியாபாரம் எப்படி?",
    "மீதம் எவ்வளவு?",
    "innaiku evlo laabam",
    "today profit evlo",
    "how much did I make today",
    "what is my profit",
    "ఈరోజు లాభం ఎంత?",
    "ఈరోజు ఎంత సంపాదించాను?",
]

NOT_AN_EXPENSE = [
    "வணக்கம்",
    "hello",
    "லட்சுமி 2000 அனுப்புனாங்க",  # money coming in
    "இன்னைக்கு 5000 வந்துச்சா?",
    "ఈరోజు 3000 వచ్చింది",
]


@pytest.mark.parametrize("text, rupees, category", EXPENSES)
def test_expense_sentences(text, rupees, category):
    r = rules.interpret(text, today=TODAY)
    assert (r.intent, r.amount_rupees, r.category, r.needs_clarification) == (E, rupees, category, False), r


@pytest.mark.parametrize("text", PROFIT)
def test_profit_questions(text):
    assert rules.interpret(text, today=TODAY).intent == P


def test_yesterday_profit_and_expense():
    assert rules.interpret("நேத்து லாபம் எவ்வளவு?", today=TODAY).day == date(2026, 11, 14)
    r = rules.interpret("நேத்து லாரி வாடகை 1500", today=TODAY)
    assert (r.intent, r.amount_rupees, r.category, r.day) == (E, 1500, TR, date(2026, 11, 14))


@pytest.mark.parametrize("text", NOT_AN_EXPENSE)
def test_not_an_expense(text):
    assert rules.interpret(text, today=TODAY).intent != E
