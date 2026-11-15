"""Matching a name as said (Tamil script or Latin letters) to the merchant's payers.

Payer names are stored in Latin letters ("Ramesh N"); a merchant says "ரமேஷ்". Both sides are reduced to a rough
sound key (Tamil letters transliterated; long vowels, aspirates and voiced/unvoiced pairs folded together, because
Tamil script writes க for both k and g, ட for t and d, ப for p and b) and compared with a similarity ratio.
Telugu script names are not transliterated yet: they match only when typed in Latin letters.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# long e and long o are written e / o (Ramesh, Gopal): in Latin names "ee" and "oo" are the i and u sounds (Meena, Pooja)
_VOWELS = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu", "எ": "e", "ஏ": "e", "ஐ": "ai",
           "ஒ": "o", "ஓ": "o", "ஔ": "au"}
_SIGNS = {"ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu", "ெ": "e", "ே": "e", "ை": "ai", "ொ": "o", "ோ": "o",
          "ௌ": "au"}
_CONSONANTS = {"க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "t", "ண": "n", "த": "th", "ந": "n", "ப": "p", "ம": "m",
               "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "l", "ள": "l", "ற": "r", "ன": "n", "ஜ": "j", "ஷ": "sh",
               "ஸ": "s", "ஹ": "h"}
_PULLI = "்"
MATCH_AT = 0.75  # a name scores at least this to be taken as that payer


def tamil_to_latin(word: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(word):
        c = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if c in _VOWELS:
            out.append(_VOWELS[c])
        elif c in _CONSONANTS:
            base = _CONSONANTS[c]
            if nxt == _PULLI:
                out.append(base)
                i += 1
            elif nxt in _SIGNS:
                out.append(base + _SIGNS[nxt])
                i += 1
            else:
                out.append(base + "a")
        elif c.isascii():
            out.append(c)
        i += 1
    return "".join(out)


def key(name: str) -> str:
    """Rough sound key: 'ரமேஷ்' and 'Ramesh' both give 'rames'."""
    s = tamil_to_latin(name.strip()).lower()
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("oo", "u"), ("ee", "i"), ("sh", "s"), ("th", "t"), ("dh", "t"), ("bh", "p"), ("ph", "p"),
                 ("kh", "k"), ("gh", "k"), ("ch", "s"), ("zh", "l"), ("w", "v")):
        s = s.replace(a, b)
    s = s.translate(str.maketrans({"g": "k", "d": "t", "b": "p", "j": "s", "z": "s", "f": "p", "q": "k", "x": "k"}))
    s = re.sub(r"([aeiou])\1+", r"\1", s)  # long vowels
    s = re.sub(r"(.)\1+", r"\1", s)  # doubled consonants
    return s


def score(heard: str, payer_name: str) -> float:
    """How well the heard word matches the payer's first name (a case ending on the heard word is tolerated)."""
    h = key(heard)
    first = key(payer_name.split()[0]) if payer_name.split() else ""
    if not h or not first:
        return 0.0
    whole = SequenceMatcher(None, h, first).ratio()
    prefix = SequenceMatcher(None, h[: len(first) + 1], first).ratio()  # ரமேஷுக்கு -> rameshuku vs ramesh
    return max(whole, prefix)
