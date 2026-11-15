from __future__ import annotations

import re

ENGLISH_SMALL = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
ENGLISH_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000}

TAMIL_SMALL = {
    "சுழியம்": 0,
    "பூஜ்ஜியம்": 0,
    "ஒன்று": 1,
    "ஒரு": 1,
    "இரண்டு": 2,
    "இரு": 2,
    "மூன்று": 3,
    "நான்கு": 4,
    "ஐந்து": 5,
    "ஆறு": 6,
    "ஏழு": 7,
    "எட்டு": 8,
    "ஒன்பது": 9,
    "பத்து": 10,
    "பதினொன்று": 11,
    "பன்னிரண்டு": 12,
    "பதின்மூன்று": 13,
    "பதினான்கு": 14,
    "பதினைந்து": 15,
    "பதினாறு": 16,
    "பதினேழு": 17,
    "பதினெட்டு": 18,
    "பத்தொன்பது": 19,
    "இருபது": 20,
    "முப்பது": 30,
    "நாற்பது": 40,
    "ஐம்பது": 50,
    "அறுபது": 60,
    "எழுபது": 70,
    "எண்பது": 80,
    "தொண்ணூறு": 90,
}
TAMIL_SCALES = {
    "நூறு": 100,
    "நூத்தி": 100,
    "ஆயிரம்": 1000,
    "ஆயிரத்து": 1000,
    "லட்சம்": 100_000,
    "கோடி": 10_000_000,
    "தொள்ளாயிரம்": 10_000,
}
TAMIL_COMPOUNDS = {
    "இருநூறு": 200,
    "மூன்றுநூறு": 300,
    "நான்குநூறு": 400,
    "ஐந்நூறு": 500,
    "ஆறுநூறு": 600,
    "ஏழுநூறு": 700,
    "எண்ணூறு": 800,
    "தொள்ளாயிரம்": 10_000,
    "இரண்டாயிரம்": 2000,
    "மூன்றாயிரம்": 3000,
    "நான்காயிரம்": 4000,
    "ஐந்தாயிரம்": 5000,
    "ஆறாயிரம்": 6000,
    "ஏழாயிரம்": 7000,
    "எட்டாயிரம்": 8000,
    "ஒன்பதாயிரம்": 9000,
    "இரு லட்சம்": 200_000,
    "மூன்று லட்சம்": 300_000,
    "நான்கு லட்சம்": 400_000,
    "ஐந்து லட்சம்": 500_000,
}

TELUGU_SMALL = {
    "సున్నా": 0,
    "ఒకటి": 1,
    "ఒక": 1,
    "రెండు": 2,
    "మూడు": 3,
    "నాలుగు": 4,
    "ఐదు": 5,
    "ఆరు": 6,
    "ఏడు": 7,
    "ఎనిమిది": 8,
    "తొమ్మిది": 9,
    "పది": 10,
    "పదిహేను": 15,
    "ఇరవై": 20,
    "ముప్పై": 30,
    "నలభై": 40,
    "అరవై": 60,
    "డెబ్బై": 70,
    "ఎనభై": 90,
}
TELUGU_SCALES = {"వంద": 100, "వెయ్యి": 1000, "వేల": 1000, "లక్ష": 100_000, "కోటి": 10_000_000}
TELUGU_COMPOUNDS = {"వంద": 100, "వెయ్యి": 1000, "లక్ష": 100_000}

ROMANIZED_WORDS = {
    "aayiram": 1000,
    "ayirathu": 1000,
    "ayiram": 1000,
    "nooru": 100,
    "nuru": 100,
    "vanda": 100,
    "veyyi": 1000,
    "laksam": 100_000,
    "laksham": 100_000,
    "lakh": 100_000,
}

NUMBER_WORDS = {
    **ENGLISH_SMALL,
    **{x.casefold(): v for x, v in ENGLISH_SMALL.items()},
    **TAMIL_SMALL,
    **TELUGU_SMALL,
    **ROMANIZED_WORDS,
}
SCALE_WORDS = {**ENGLISH_SCALES, **TAMIL_SCALES, **TELUGU_SCALES}


def _normalize_text(raw: str) -> str:
    text = raw.strip()
    replacements = {
        "₹": " ",
        "Rs": " ",
        "rs": " ",
        "rupees": " ",
        "rupes": " ",
        "ரூபாய்": " ",
        "ரூபாயை": " ",
        "ரூ": " ",
        "–": " ",
        "—": " ",
        "-": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_numeric_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z\u0B80-\u0BFF\u0C00-\u0C7F]+", text, flags=re.UNICODE)


def _parse_word_tokens(tokens: list[str]) -> int:
    total = 0
    current = 0
    for token in tokens:
        key = token.strip().casefold()
        if not key:
            continue
        if key in {"and", "&", "மற்றும்", "మరియు"}:
            continue
        if key in SCALE_WORDS:
            scale = int(SCALE_WORDS[key])
            if scale == 100:
                if current == 0:
                    current = 100
                else:
                    current *= 100
                continue
            if current == 0:
                current = scale
            else:
                total += current * scale
                current = 0
            continue
        if key in NUMBER_WORDS:
            current += int(NUMBER_WORDS[key])
            continue
        if key in TAMIL_COMPOUNDS or key in TELUGU_COMPOUNDS:
            total += int(TAMIL_COMPOUNDS.get(key, TELUGU_COMPOUNDS.get(key, 0)))
            current = 0
            continue
        if key.endswith("k") and key[:-1].isdigit():
            total += int(key[:-1]) * 1000
            current = 0
            continue
    total += current
    if total == 0 and current == 0:
        raise ValueError(f"Could not parse amount from {tokens!r}")
    return total


def parse_amount(span: str) -> int:
    """Parse a rupee amount represented as digits, English words or Indian/Telugu/Tamil words.

    Returns the rupee amount as an integer. Callers may scale to paise if required.
    """
    if span is None or not isinstance(span, str):
        raise TypeError("amount span must be a string")

    text = _normalize_text(span)
    if not text:
        raise ValueError("Empty amount span")

    digits_candidate = text.replace(",", "").replace(" ", "")
    if re.fullmatch(r"\d+", digits_candidate):
        value = int(digits_candidate)
        if value < 1 or value > 500_000:
            raise ValueError(f"Amount out of range: {value}")
        return value

    if re.fullmatch(r"\d+k", text, flags=re.IGNORECASE):
        value = int(float(text[:-1]) * 1000)
        if value < 1 or value > 500_000:
            raise ValueError(f"Amount out of range: {value}")
        return value

    tokens = _extract_numeric_tokens(text)
    if not tokens:
        raise ValueError(f"Could not parse amount: {span!r}")

    value = _parse_word_tokens(tokens)
    if value < 1 or value > 500_000:
        raise ValueError(f"Amount out of range: {value}")
    return value
