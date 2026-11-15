"""Daily profit answer (VOICE_AND_NOTICE 4.3, 6, 7; contract section 6 POST /voice/answer). Owner: Asitha.

Money is spoken only through the fixed templates in templates/{lang}.json, filled with facts from
finance.summary.compute. A positional slot check runs before TTS: each template key has a fixed slot order, the
text in every slot must equal the speech form of its own fact, and no other digits may appear. A failed check is a
template bug: 500, never speech. A missing figure (absent, None, or not integer paise / a count) is also a 500 and
never spoken: nothing is said unless every backend value is there. The LLM is not involved.
"""
from __future__ import annotations

import json
import re
import sqlite3
import string
from datetime import date
from functools import lru_cache
from pathlib import Path

from .. import clock, errors, money, repo
from ..finance.summary import compute
from ..questions_text import spoken_amount
from ..sarvam import client as sarvam

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SCOPE_NOTE = "UPI payments only. Profit = business sales minus expenses you entered."
# fixed slot order per template key (positional, not a set)
SLOT_ORDER = {
    "profit_answer": ("sales", "expenses", "profit"),
    "profit_answer_loss": ("sales", "expenses", "loss"),
    "profit_family_suffix": ("family",),
    "profit_pending_suffix": ("pending_count",),
}
DIGITS = re.compile(r"\d")
# every figure finance.summary.compute must supply before anything is spoken
FIGURES = ("business_sales", "expenses", "profit", "family_transfers", "pending_count")


class SlotCheckFailed(Exception):
    pass


class MissingFigure(SlotCheckFailed):
    """A backend figure is absent, None, or not an int (paise, or a count)."""


@lru_cache
def templates(lang: str) -> dict:
    path = TEMPLATES_DIR / f"{lang}.json"
    if not path.exists():
        raise errors.validation_error(f"No voice templates for language {lang!r} yet (templates/{lang}.json)",
                                      field="language")
    return json.loads(path.read_text(encoding="utf-8"))


def speech(slot: str, value: int, lang: str) -> str:
    """The speech form of a slot value: amounts as '4,820 ரூபாய்', counts as digits."""
    return str(value) if slot == "pending_count" else spoken_amount(value, lang)


def render(template: str, key: str, values: dict, lang: str) -> tuple[str, list[tuple[str, int, int]]]:
    """Fill the template and record (slot, start, end) of every placeholder in the produced text."""
    out, spans = "", []
    for literal, field, _, _ in string.Formatter().parse(template):
        out += literal
        if field is None:
            continue
        if field not in values:
            raise SlotCheckFailed(f"{key}: unknown slot {{{field}}}")
        start = len(out)
        out += speech(field, values[field], lang)
        spans.append((field, start, len(out)))
    return out, spans


def slot_check(parts: list[tuple[str, str, list]], values: dict, lang: str) -> None:
    """parts: (key, text, spans) in order. Raises SlotCheckFailed on any positional mismatch."""
    for key, text, spans in parts:
        names = tuple(s[0] for s in spans)
        if names != SLOT_ORDER[key]:
            raise SlotCheckFailed(f"{key}: slots {names}, expected {SLOT_ORDER[key]}")
        rest = text
        for slot, start, end in sorted(spans, key=lambda s: -s[1]):
            if text[start:end] != speech(slot, values[slot], lang):
                raise SlotCheckFailed(f"{key}: slot {slot} holds {text[start:end]!r}")
            rest = rest[:start] + rest[end:]
        if DIGITS.search(rest):
            raise SlotCheckFailed(f"{key}: digits outside the slots in {rest!r}")


def compose(facts: dict, lang: str) -> tuple[str, dict]:
    """(text, slot values in paise / count). Raises MissingFigure before rendering anything when a figure is
    missing, SlotCheckFailed on a template bug."""
    missing = [k for k in FIGURES if type(facts.get(k)) is not int]  # bool and float are not figures either
    if missing:
        raise MissingFigure(f"missing figure(s): {', '.join(missing)}")
    t = templates(lang)
    values = {"sales": facts["business_sales"], "expenses": facts["expenses"], "family": facts["family_transfers"],
              "pending_count": facts["pending_count"]}
    if facts["profit"] >= 0:
        key, values["profit"] = "profit_answer", facts["profit"]
    else:
        key, values["loss"] = "profit_answer_loss", -facts["profit"]
    keys = [key]
    if facts["family_transfers"] > 0:
        keys.append("profit_family_suffix")
    if facts["pending_count"] > 0:
        keys.append("profit_pending_suffix")  # must say how many payments are still unconfirmed
    parts = []
    for k in keys:
        text, spans = render(t[k], k, values, lang)
        parts.append((k, text, spans))
    slot_check(parts, values, lang)
    used = {s for k in keys for s in SLOT_ORDER[k]}
    return " ".join(p[1] for p in parts), {s: values[s] for s in ("sales", "expenses", "profit", "loss", "family",
                                                                    "pending_count") if s in used}


def daily_profit(conn: sqlite3.Connection, *, merchant_id: str, language: str, day: date | None = None) -> dict:
    repo.require_merchant_in_body(conn, merchant_id)
    day = day or clock.today()
    if day != clock.today():
        raise errors.validation_error("Only today's profit has a spoken template so far (VOICE_AND_NOTICE 7)",
                                      field="date")
    b = compute(conn, merchant_id, day, day)
    facts = {k: getattr(b, k, None) for k in FIGURES}  # an absent figure is caught by compose, not here
    try:
        text, slots = compose(facts, language)
    except MissingFigure as exc:
        raise errors.ApiError(500, "INTERNAL_ERROR", f"Slot check failed ({exc}); nothing was spoken")
    except SlotCheckFailed as exc:
        raise errors.ApiError(500, "INTERNAL_ERROR", f"Slot check failed (template bug): {exc}")
    audio_id, from_cache, audio_error = None, False, None
    try:
        tts = sarvam.tts(text, language)
        audio_id, from_cache = tts.audio_id, tts.from_cache
    except errors.ApiError as exc:  # no speech, the screen still shows the text and numbers
        audio_error = exc.code
    return {
        "text": text,
        "language": language,
        "facts": {
            "business_sales": money.amount(b.business_sales),
            "expenses": money.amount(b.expenses),
            "profit": money.amount(b.profit),
            "family_transfers": money.amount(b.family_transfers),
            "pending_count": b.pending_count,
        },
        "number_check": {"passed": True, "slots": slots},
        "scope_note": SCOPE_NOTE,
        "audio_id": audio_id,
        "from_cache": from_cache,
        "audio_error": audio_error,
    }
