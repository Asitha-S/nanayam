"""Deterministic voice interpretation (VOICE_AND_NOTICE 5.2, 5.3, 5.4). Owner: Asitha. The Tamil
keyword rows were drafted and checked by Asitha; the Telugu rows were drafted with Claude Code and
reviewed by Nagasai Sree (edit KEYWORDS below).

- parse_amount(span) -> whole rupees, from digits ("3,100", "3100", "3 100", "1,50,000"), "k" ("3k", "2.5k"),
  English words ("three thousand one hundred"), Tamil and Telugu number words, romanized forms, and fractions
  (அரை, கால், முக்கால், ஒண்ணரை, ரெண்டரை … ; అర, పావు, ముప్పావు, ఒకటిన్నర …). Raises ValueError otherwise.
- find_amount(text) -> (span, rupees) for the first span parse_amount can read, or None.
- KEYWORDS: the 5.4 tables. interpret(...): the 5.3 rule-based interpreter with the 5.2 checks.

No LLM here: the result is a pure function of the text (and the open question's state).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

MIN_RUPEES, MAX_RUPEES = 1, 500_000

# ---------------------------------------------------------------------------------------------------------------
# Number words. Each word expands to atoms: a number (added to the running value), or a multiplier
# H (×100), K (×1,000, closes a group), L (×1,00,000, closes a group).
H, K, L = "H", "K", "L"

_UNITS = {
    # Tamil
    "ஒன்று": 1, "ஒண்ணு": 1, "ஒரு": 1, "இரண்டு": 2, "ரெண்டு": 2, "இரு": 2, "மூன்று": 3, "மூணு": 3, "நான்கு": 4,
    "நாலு": 4, "ஐந்து": 5, "அஞ்சு": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50, "அம்பது": 50, "அறுபது": 60, "எழுபது": 70,
    "எண்பது": 80, "தொண்ணூறு": 90,
    "இருபத்து": 20, "இருபத்தி": 20, "முப்பத்து": 30, "முப்பத்தி": 30, "நாற்பத்து": 40, "நாற்பத்தி": 40,
    "ஐம்பத்து": 50, "ஐம்பத்தி": 50, "அறுபத்து": 60, "அறுபத்தி": 60, "எழுபத்து": 70, "எழுபத்தி": 70,
    "எண்பத்து": 80, "எண்பத்தி": 80, "தொண்ணூற்று": 90, "தொண்ணூத்தி": 90,
    # Telugu
    "ఒకటి": 1, "ఒక": 1, "రెండు": 2, "మూడు": 3, "నాలుగు": 4, "ఐదు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8,
    "తొమ్మిది": 9, "పది": 10, "ఇరవై": 20, "ముప్పై": 30, "నలభై": 40, "యాభై": 50, "అరవై": 60, "డెబ్బై": 70,
    "ఎనభై": 80, "తొంభై": 90,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    # romanized Tamil / Telugu
    "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "aaru": 6, "ezhu": 7, "ettu": 8, "onbadhu": 9,
    "pathu": 10, "patthu": 10, "irubathu": 20, "muppathu": 30, "aimbathu": 50, "ambathu": 50,
    "okati": 1, "moodu": 3, "naalugu": 4, "aidu": 5, "padi": 10, "iravai": 20, "yaabhai": 50,
}
_FRACTIONS = {
    "அரை": 0.5, "கால்": 0.25, "முக்கால்": 0.75, "ஒண்ணரை": 1.5, "ஒன்றரை": 1.5, "ரெண்டரை": 2.5, "இரண்டரை": 2.5,
    "மூணரை": 3.5, "நாலரை": 4.5, "அஞ்சரை": 5.5,
    "అర": 0.5, "పావు": 0.25, "ముప్పావు": 0.75, "ఒకటిన్నర": 1.5, "ఒకటిన్నర్": 1.5, "రెండున్నర": 2.5,
    "మూడున్నర": 3.5, "నాలుగున్నర": 4.5,
    "half": 0.5, "arai": 0.5, "mukkaal": 0.75, "onnarai": 1.5, "rendarai": 2.5, "moonarai": 3.5,
}
_MULTIPLIERS = {
    H: ["நூறு", "நூத்தி", "நூற்று", "நூத்து", "వంద", "వందల", "వందలు", "నూట", "hundred", "nooru", "noothi", "vanda", "vandala"],
    K: ["ஆயிரம்", "ஆயிரத்து", "ஆயிரத்தி", "வெயிரம்", "వెయ్యి", "వేల", "వేలు", "thousand", "aayiram", "ayiram",
        "aayirathu", "ayirathu", "aayirathi", "veyyi", "velu", "vela"],
    L: ["லட்சம்", "லட்சத்து", "லட்ச", "లక్ష", "లక్షల", "లక్షలు", "lakh", "lakhs", "laksham", "latcham", "laksha"],
}
# Tamil fused forms: hundreds and thousands written as one word.
_FUSED = {
    "இருநூறு": [2, H], "இருநூத்தி": [2, H], "முந்நூறு": [3, H], "முன்னூறு": [3, H], "முன்னூத்தி": [3, H],
    "நானூறு": [4, H], "நாநூறு": [4, H], "நானூத்தி": [4, H], "ஐநூறு": [5, H], "ஐநூத்தி": [5, H],
    "அஞ்சுநூறு": [5, H], "அறுநூறு": [6, H], "அறுநூத்தி": [6, H], "எழுநூறு": [7, H], "எழுநூத்தி": [7, H],
    "எண்ணூறு": [8, H], "எண்ணூத்தி": [8, H], "தொள்ளாயிரம்": [9, H], "தொள்ளாயிரத்து": [9, H],
    "ரெண்டாயிரம்": [2, K], "ரெண்டாயிரத்து": [2, K], "இரண்டாயிரம்": [2, K], "இரண்டாயிரத்து": [2, K],
    "மூவாயிரம்": [3, K], "மூவாயிரத்து": [3, K], "மூணாயிரம்": [3, K], "மூணாயிரத்து": [3, K],
    "நாலாயிரம்": [4, K], "நாலாயிரத்து": [4, K], "நான்காயிரம்": [4, K], "ஐயாயிரம்": [5, K], "ஐயாயிரத்து": [5, K],
    "அஞ்சாயிரம்": [5, K], "அஞ்சாயிரத்து": [5, K], "ஆறாயிரம்": [6, K], "ஆறாயிரத்து": [6, K],
    "ஏழாயிரம்": [7, K], "ஏழாயிரத்து": [7, K], "எட்டாயிரம்": [8, K], "எட்டாயிரத்து": [8, K],
    "ஒன்பதாயிரம்": [9, K], "பத்தாயிரம்": [10, K], "பத்தாயிரத்து": [10, K],
    "irunooru": [2, H], "munnooru": [3, H], "naanooru": [4, H], "ainooru": [5, H], "rendaayiram": [2, K],
    "moovaayiram": [3, K], "moonaayiram": [3, K], "naalaayiram": [4, K], "anjaayiram": [5, K],
}

WORD_ATOMS: dict[str, list] = {}
for _w, _v in {**_UNITS, **_FRACTIONS}.items():
    WORD_ATOMS[_w.casefold()] = [_v]
for _m, _words in _MULTIPLIERS.items():
    for _w in _words:
        WORD_ATOMS[_w.casefold()] = [_m]
for _w, _atoms in _FUSED.items():
    WORD_ATOMS[_w.casefold()] = list(_atoms)
_CONNECTORS = {"and", "um", "ம்"}  # "two thousand and fifty"; ignored inside a number
# case endings that may follow a number word ("ஆயிரத்துக்கு", "aayiram-ku")
_SUFFIXES = ("க்கு", "கு", "ல", "ku", "kku", "ki", "కి", "కు")

_TOKEN = re.compile(r"[^\s,.;:!?\-–—/()\[\]\"'“”‘’₹]+")
_DIGITS = re.compile(
    r"(?<![\w.])("
    r"\d+(?:\.\d+)?\s?[kK](?![\w])"                    # 3k, 2.5k, 3 k
    r"|\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?"            # 3,100  1,50,000
    r"|\d+(?: \d{3})+"                                 # 3 100
    r"|\d+(?:\.\d{1,2})?"                              # 3100
    r")(?!\d)"
)


def _atoms_for(token: str) -> list | None:
    t = token.casefold()
    if t in WORD_ATOMS:
        return WORD_ATOMS[t]
    for suf in _SUFFIXES:
        if t.endswith(suf) and t[: -len(suf)] in WORD_ATOMS:
            return WORD_ATOMS[t[: -len(suf)]]
    return None


def _value_of_atoms(atoms: list) -> float:
    total, current = 0.0, 0.0
    for a in atoms:
        if a == H:
            current = (current or 1) * 100
        elif a in (K, L):
            total += (current or 1) * (1000 if a == K else 100_000)
            current = 0.0
        else:
            current += a
    return total + current


def _whole(value: float) -> int:
    if value <= 0 or abs(value - round(value)) > 1e-9:
        raise ValueError(f"not a whole number of rupees: {value}")
    return int(round(value))


def parse_amount(span: str) -> int:
    """Whole rupees for an amount span. Raises ValueError when the span is not an amount."""
    s = (span or "").strip()
    if not s:
        raise ValueError("empty amount")
    m = _DIGITS.fullmatch(s)
    if m:
        txt = m.group(1).replace(",", "").replace(" ", "")
        if txt[-1] in "kK":
            return _whole(float(txt[:-1]) * 1000)
        return _whole(float(txt))
    atoms: list = []
    for tok in _TOKEN.findall(s):
        if tok.casefold() in _CONNECTORS:
            continue
        a = _atoms_for(tok)
        if a is None:
            raise ValueError(f"not a number word: {tok!r}")
        atoms.extend(a)
    if not atoms:
        raise ValueError("no number")
    return _whole(_value_of_atoms(atoms))


def _word_runs(text: str):
    """Spans of consecutive number words (connectors allowed inside), as written, in text order."""
    tokens = list(_TOKEN.finditer(text))
    i = 0
    while i < len(tokens):
        if _atoms_for(tokens[i].group()) is None:
            i += 1
            continue
        j = i
        while j + 1 < len(tokens) and (_atoms_for(tokens[j + 1].group()) is not None
                                       or (tokens[j + 1].group().casefold() in _CONNECTORS and j + 2 < len(tokens)
                                           and _atoms_for(tokens[j + 2].group()) is not None)):
            j += 1
        yield text[tokens[i].start():tokens[j].end()]
        i = j + 1


def _is_article(span: str) -> bool:
    """A lone small number word ("ஒரு ஆட்டோ", "one auto") is an article, not an amount."""
    atoms = [a for t in _TOKEN.findall(span) for a in (_atoms_for(t) or [])]
    return len(atoms) == 1 and isinstance(atoms[0], int) and atoms[0] < 10


def find_amount(text: str) -> tuple[str, int] | None:
    """The amount span in the text and its rupees, or None. Digits win when present (the merchant said a figure);
    otherwise the first run of number words that parses (a lone small word like "ஒரு" is an article, skipped)."""
    m = _DIGITS.search(text)
    if m:
        try:
            return m.group(1), parse_amount(m.group(1))
        except ValueError:
            pass
    for span in _word_runs(text):
        if _is_article(span):
            continue
        try:
            return span, parse_amount(span)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------------------------------------------
# Keyword tables (VOICE_AND_NOTICE 5.4). Matching: a word of the text starts with the keyword (case-insensitive),
# so suffixes like வாங்கினேன் / Koyambedu-la still match. A keyword written "=word" must be the whole word, or the word
# plus a case ending (பை, பைக்கு: a bag; never பையன், a boy).
KEYWORDS: dict[str, tuple[str, ...]] = {
    "STOCK_PURCHASE": ("காய்கறி", "சரக்கு", "வாங்கி", "கோயம்பேடு", "தக்காளி", "வெங்காய", "உருளை", "பழம்", "பழங்", "கீரை",
                       "மார்க்கெட்", "மண்டி", "kaaikari", "kaykari", "sarakku", "vaangi", "koyambedu", "thakkali",
                       "vengayam", "market", "stock", "vegetable", "fruit", "tomato", "onion",
                       "కూరగాయలు", "పండ్లు", "సరుకు", "కొన్నాను", "టమాట", "ఉల్లి", "మార్కెట్", "kooragayalu", "pandlu",
                       "konnanu"),
    "TRANSPORT": ("வண்டி", "ஆட்டோ", "லாரி", "பெட்ரோல்", "டீசல்", "பஸ்", "டெம்போ", "vandi", "auto", "lorry",
                  "petrol", "diesel", "=bus", "tempo", "transport", "fare", "ఆటో", "లారీ", "బండి", "పెట్రోల్", "డీజిల్",
                  "బస్"),
    "PACKAGING": ("கவர்", "=பை", "பேப்பர்", "பாக்கெட்", "cover", "=pai", "bag", "packing", "packaging", "=box",
                  "కవర్", "సంచి", "ప్యాకింగ్"),
    "RENT": ("வாடகை", "vaadagai", "=rent", "అద్దె", "adde"),
    "WAGES": ("கூலி", "சம்பளம்", "பையன்", "வேலைக்கார", "kooli", "sambalam", "paiyan", "salary", "wage", "helper",
              "కూలి", "జీతం", "పనివాడు"),
    "UTILITIES": ("கரண்ட்", "தண்ணி", "தண்ணீர்", "கேஸ்", "=eb", "current", "water", "=gas", "electricity",
                  "కరెంట్", "నీళ్లు", "గ్యాస్"),
    "FAMILY": ("வீட்டு", "வீடு", "குடும்ப", "அக்கா", "அண்ணன்", "தம்பி", "அம்மா", "அப்பா", "veettu", "veedu", "akka",
               "=anna", "thambi", "amma", "appa", "ఇంటి", "ఇల్లు", "ఇంట్లో", "కుటుంబం", "అక్క", "అన్న", "తమ్ముడు",
               "అమ్మ"),
    "SALE": ("கடை", "வியாபாரம்", "விற்பனை", "கஸ்டமர்", "kadai", "vyaabaaram", "viyabaram", "customer", "షాప్",
             "కొట్టు", "అమ్మకం", "వ్యాపారం", "కస్టమర్"),
    "YES": ("ஆமா", "ஆம்", "சரி", "ஓகே", "கரெக்ட்", "aamaa", "aama", "sari", "=ok", "okay", "అవును", "సరే", "ఓకే"),
    "NO": ("இல்ல", "வேண்டாம்", "தப்பு", "illa", "vendaam", "కాదు", "వద్దు", "తప్పు"),
    "REMEMBER": ("எப்பவும்", "இனிமே", "எல்லாமே", "eppavum", "inime", "ఎప్పుడూ", "ఇకపై", "అన్నీ"),
    "YESTERDAY": ("நேத்து", "நேற்று", "nethu", "yesterday", "నిన్న", "ninna"),
    # intent words (5.3)
    "PROFIT": ("லாபம்", "மீதம்", "கணக்கு", "labham", "laabam", "meedham", "lābhaṁ", "profit", "లాభం", "మిగిలింది"),
    # money going out. Stems, so every form matches: செலவு, செலவானது, செலவாச்சு, செலவழிச்சேன்; ఖర్చు, ఖర్చైంది
    "EXPENSE": ("வாங்கி", "வாங்கின", "வாங்க", "செலவ", "கொடுத்", "குடுத்", "கட்டின", "போட்டேன்", "kharch", "selav",
                "vaangi", "vaangu", "kuduth", "koduth", "kattin", "potten", "spent", "spend", "=paid", "=pay",
                "bought", "=buy", "=gave", "purchase", "expense", "ఖర్చ", "konnanu", "కొన్నాను", "ఇచ్చాను",
                "కట్టాను", "పెట్టాను"),
    # money coming in: never an expense ("லட்சுமி 2000 அனுப்புனாங்க")
    "INCOME": ("வந்து", "வந்த", "வந்திருக்கு", "அனுப்பு", "அனுப்பின", "கிடைச்ச", "கிடைத்த", "வித்தேன்", "vandhu",
               "vanthu", "anuppu", "kedachu", "received", "=got", "came", "sold", "వచ్చ", "పంపా", "పంపించ"),
    # how much did I earn / how was business (with a question word, and no rupee figure): a profit question
    "EARN": ("சம்பாதி", "வருமான", "வசூல்", "கல்லா", "sambadh", "sambaadh", "varumaan", "=earn", "earned", "=make",
             "=made", "income", "సంపాద", "ఆదాయం"),
    "QUESTION": ("எவ்வளவு", "எப்படி", "evlo", "evvalavu", "eppadi", "=how", "=what", "ఎంత", "ఎలా"),
    # udhari (UDHARI flag only): credit given, and "who owes me"
    "CREDIT": ("கடன்", "கடனா", "கடனு", "உதாரி", "உத்தாரி", "பாக்கி", "எழுது", "எழுதி", "kadan", "udhari", "udhaar",
               "=udhar", "baaki", "=baki", "ezhuth", "ezhudh", "=credit", "=tab", "=dues", "అప్పు", "ఉద్దెర", "ఉద్దర",
               "బాకీ", "=appu", "uddera", "రాయి", "రాసు"),
    "OWE": ("தரணும்", "குடுக்கணும்", "கொடுக்கணும்", "tharanum", "tharanam", "kudukkanum", "kodukkanum", "=owe", "owes",
            "=owed", "=owing", "ఇవ్వాలి", "ivvali"),
    "WHO": ("யார்", "யாரு", "யாரெல்லாம்", "yaar", "yaaru", "yaarellam", "=who", "ఎవరు", "ఎవరెవరు", "evaru", "evarevaru"),
}
# words that are never a person's name in "ரமேஷ் 300 கடன்" (amount words and keywords are skipped too)
NAME_FILLERS = {"ரூபாய்", "ரூபா", "ரூ", "கணக்குல", "கணக்கில்", "கணக்கு", "பேர்ல", "rupees", "rupee", "rs", "ku", "kku",
                "la", "le", "kanakku", "kanakkula", "account", "on", "to", "for", "his", "her", "the", "a", "an", "in",
                "write", "put", "add", "give", "gave", "please", "இன்னைக்கு", "இன்னிக்கு", "innaiku", "today",
                "రూపాయలు", "రూ", "ఖాతాలో", "ఖాతా", "ఈరోజు"}
_CASE_ENDINGS = ("", "க்கு", "கு", "ல", "ல்", "யில", "யில்", "ku", "kku", "la", "s", "కి", "లో")
EXPENSE_CATEGORIES = ("STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT", "WAGES", "UTILITIES", "OTHER")
_VERBS = set(KEYWORDS["EXPENSE"])  # matched words that describe the act, not the thing (kept out of descriptions)


def _words(text: str) -> list[str]:
    return _TOKEN.findall(text)


def _hit(word: str, key: str) -> bool:
    if key.startswith("="):
        k = key[1:]
        return word.startswith(k) and word[len(k):] in _CASE_ENDINGS
    return word.startswith(key)


def matches(text: str, group: str) -> list[str]:
    """Words of the text (as written) that match a keyword group, in text order."""
    keys = [k.casefold() for k in KEYWORDS[group]]
    return [w for w in _words(text) if any(_hit(w.casefold(), k) for k in keys)]


def category_of(text: str) -> str | None:
    """Expense category by keyword count (table order breaks ties); None when no category keyword is present."""
    best, best_n = None, 0
    for cat in EXPENSE_CATEGORIES[:-1]:
        n = len(matches(text, cat))
        if n > best_n:
            best, best_n = cat, n
    return best


# ---------------------------------------------------------------------------------------------------------------
# Templates (VOICE_AND_NOTICE 7). Category words match the Talk screen.
TEXTS = {
    "ta": {
        "expense_confirm": "{amount} {category} செலவு ({description}). சரியா?",
        "clarify_amount": "எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க.",
        "clarify_category": "கடை வியாபாரமா, வீட்டு பணமா? கீழ தட்டுங்க.",
        "not_understood": "புரியல. செலவு சொல்லுங்க, இல்லன்னா இன்னைக்கு லாபம் கேளுங்க.",
        "categories": {"STOCK_PURCHASE": "சரக்கு", "TRANSPORT": "வண்டி", "PACKAGING": "கவர்", "RENT": "வாடகை",
                       "WAGES": "கூலி", "UTILITIES": "கரண்ட்/தண்ணி", "OTHER": "மற்ற"},
    },
    "te": {
        "expense_confirm": "{amount} {category} ఖర్చు ({description}). సరేనా?",
        "clarify_amount": "ఎంత రూపాయలో మళ్ళీ ఒకసారి చెప్పండి.",
        "clarify_category": "షాప్ అమ్మకమా, ఇంటి డబ్బా? కింద నొక్కండి.",
        "not_understood": "అర్థం కాలేదు. ఖర్చు చెప్పండి, లేదా ఈరోజు లాభం అడగండి.",
        "categories": {"STOCK_PURCHASE": "సరుకు", "TRANSPORT": "బండి", "PACKAGING": "కవర్", "RENT": "అద్దె",
                       "WAGES": "కూలి", "UTILITIES": "కరెంట్/నీళ్లు", "OTHER": "ఇతర"},
    },
}


@dataclass
class OpenQuestion:
    """The question card the utterance answers. answered_category: the payment's current answer if the question
    was already answered (the remember prompt), else None."""
    question_id: str
    answered_category: str | None = None


@dataclass
class Reading:
    """The rule interpreter's result before it is shaped into the API response."""
    intent: str
    amount_span: str | None = None
    amount_rupees: int | None = None
    category: str | None = None
    description: str = ""
    day: date | None = None
    confirmed_category: str | None = None
    remember_payer: bool = False
    payer_heard: str | None = None  # ADD_CREDIT: the name as said
    needs_clarification: bool = False
    clarification_key: str | None = None
    notes: list[str] = field(default_factory=list)


def heard_name(text: str, amount_span: str | None) -> str | None:
    """The first word that is not the amount, a keyword or a filler: the person in "ரமேஷ் 300 கடன்"."""
    skip = {w.casefold() for w in _words(amount_span or "")}
    for w in _words(text):
        f = w.casefold()
        if f in skip or f in NAME_FILLERS or any(ch.isdigit() for ch in w):
            continue
        if any(_hit(f, k.casefold()) for group in KEYWORDS.values() for k in group):
            continue
        try:
            parse_amount(w)
            continue  # a number word
        except ValueError:
            pass
        return w
    return None


def interpret(text: str, *, today: date, open_question: OpenQuestion | None = None, udhari: bool = False) -> Reading:
    """Rule-based interpreter (5.3) with the 5.2 checks. Deterministic. udhari: the UDHARI flag (two more intents)."""
    day = today - timedelta(days=1) if matches(text, "YESTERDAY") else today
    fam, sale = matches(text, "FAMILY"), matches(text, "SALE")
    remember = bool(matches(text, "REMEMBER"))

    # answering the open question card
    if open_question is not None:
        if fam and sale:
            return Reading("CONFIRM_TRANSACTION", day=day, remember_payer=remember, needs_clarification=True,
                           clarification_key="clarify_category", notes=["both sale and family words"])
        if fam or sale:
            return Reading("CONFIRM_TRANSACTION", day=day, confirmed_category="FAMILY" if fam else "SALE",
                           remember_payer=remember)
        # the remember prompt ("ஆமா, எப்பவும்"): the answer stands; yes/remember means remember it
        if open_question.answered_category and (matches(text, "YES") or remember or matches(text, "NO")):
            return Reading("CONFIRM_TRANSACTION", day=day, confirmed_category=open_question.answered_category,
                           remember_payer=not matches(text, "NO") and bool(remember or matches(text, "YES")))

    found = find_amount(text)
    category = category_of(text)
    expense_words = matches(text, "EXPENSE")
    income = matches(text, "INCOME")
    asks = bool(matches(text, "QUESTION")) or "?" in text
    if udhari:
        credit, who, owe = matches(text, "CREDIT"), matches(text, "WHO"), matches(text, "OWE")
        # "யாரெல்லாம் பணம் தரணும்?", "who owes me", "baaki evlo?"
        if not found and ((who and (owe or credit)) or (asks and credit) or (owe and asks)):
            return Reading("ASK_DUES", day=day)
        # "ரமேஷ் 300 கடன்", "Ramesh 300 udhari", "ரமேஷுக்கு 300 கடன் குடுத்தேன்": credit wins over the giving verb
        if credit and not income:
            span, rupees = found if found else (None, None)
            name = heard_name(text, span)
            if not found:
                return Reading("ADD_CREDIT", payer_heard=name, day=day, needs_clarification=True,
                               clarification_key="clarify_amount", notes=["no amount in the text"])
            if not (MIN_RUPEES <= rupees <= MAX_RUPEES):
                return Reading("ADD_CREDIT", amount_span=span, payer_heard=name, day=day, needs_clarification=True,
                               clarification_key="clarify_amount", notes=[f"amount {rupees} out of range"])
            return Reading("ADD_CREDIT", amount_span=span, amount_rupees=rupees, payer_heard=name, day=day,
                           needs_clarification=name is None, clarification_key=None if name else "clarify_payer")
    if matches(text, "PROFIT") and not (found and (expense_words or category)):
        return Reading("ASK_DAILY_PROFIT", day=day)
    # "இன்னைக்கு எவ்வளவு சம்பாதிச்சேன்?", "how much did I make today", "இன்னைக்கு வியாபாரம் எப்படி?"
    if not found and not expense_words and (matches(text, "EARN") or (asks and sale)):
        return Reading("ASK_DAILY_PROFIT", day=day)
    # Read generously: every expense goes to a confirmation card and nothing is saved until the merchant says yes.
    # A rupee figure is an expense unless the money came in or the sentence asks about it.
    if expense_words or (found and category) or (found and not income and not asks):
        desc_words = [w for w in matches(text, category) if not w.casefold().startswith(tuple(v.casefold() for v in _VERBS))] if category else []
        description = ", ".join(_clean(w) for w in desc_words)
        if not found:
            return Reading("LOG_EXPENSE", category=category or "OTHER", description=description, day=day,
                           needs_clarification=True, clarification_key="clarify_amount", notes=["no amount in the text"])
        span, rupees = found
        if not (MIN_RUPEES <= rupees <= MAX_RUPEES):
            return Reading("LOG_EXPENSE", amount_span=span, category=category or "OTHER", description=description,
                           day=day, needs_clarification=True, clarification_key="clarify_amount",
                           notes=[f"amount {rupees} outside ₹{MIN_RUPEES}–₹{MAX_RUPEES:,}"])
        return Reading("LOG_EXPENSE", amount_span=span, amount_rupees=rupees, category=category or "OTHER",
                       description=description, day=day)
    return Reading("UNKNOWN", day=day, needs_clarification=True, clarification_key="not_understood")


def _clean(word: str) -> str:
    w = word
    for suf in ("-la", "-ku", "-le"):
        if w.casefold().endswith(suf):
            w = w[: -len(suf)]
    return w[:1].upper() + w[1:] if w.isascii() else w
