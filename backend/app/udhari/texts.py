"""Fixed sentences for udhari (no LLM). Amounts come from money.display through spoken_amount. Tamil: Asitha's draft for
Charulatha to check; Telugu: draft for Nagasai Sree to check."""
from __future__ import annotations

from .. import money
from ..questions_text import spoken_amount

TEXTS = {
    "ta": {
        "credit_confirm": "{name} கணக்குல {amount} கடன் எழுதவா?",
        "clarify_payer": "யார் கணக்குல எழுதணும்? பேர் சொல்லுங்க.",
        "offer": "{name} {payment} கொடுத்திருக்காங்க. கடன் கணக்குல கழிக்கவா? பாக்கி {due}.",
        "dues": "{count} பேர் மொத்தம் {total} தரணும்.",
        "dues_none": "இப்போ யாரும் கடன் பாக்கி வைக்கல.",
    },
    "te": {
        "credit_confirm": "{name} ఖాతాలో {amount} అప్పు రాయనా?",
        "clarify_payer": "ఎవరి ఖాతాలో రాయాలి? పేరు చెప్పండి.",
        "offer": "{name} {payment} ఇచ్చారు. అప్పు ఖాతాలో తీసేయనా? బాకీ {due}.",
        "dues": "{count} మంది మొత్తం {total} ఇవ్వాలి.",
        "dues_none": "ఇప్పుడు ఎవరికీ బాకీ లేదు.",
    },
}
MAX_NAMED = 6  # the spoken list names at most this many people


def _lang(language: str | None) -> str:
    return language if language in TEXTS else "ta"


def credit_confirm(language: str | None, name: str, paise: int) -> str:
    lang = _lang(language)
    return TEXTS[lang]["credit_confirm"].format(name=name, amount=spoken_amount(paise, lang))


def clarify_payer(language: str | None) -> str:
    return TEXTS[_lang(language)]["clarify_payer"]


def offer(language: str | None, name: str, payment_paise: int, due_paise: int) -> tuple[str, str]:
    """(text in the language, English text for a device voice without it)."""
    lang = _lang(language)
    text = TEXTS[lang]["offer"].format(name=name, payment=spoken_amount(payment_paise, lang), due=spoken_amount(due_paise, lang))
    plain = lambda p: money.display(p).replace(money.RUPEE, "")  # noqa: E731
    return text, f"{name} paid {plain(payment_paise)} rupees. Take it off the tab? {plain(due_paise)} rupees due."


def dues(language: str | None, open_items: list[dict], total_paise: int) -> str:
    """open_items: [{payer_name, due_paise}] oldest first."""
    lang = _lang(language)
    if not open_items:
        return TEXTS[lang]["dues_none"]
    head = TEXTS[lang]["dues"].format(count=len(open_items), total=spoken_amount(total_paise, lang))
    named = ", ".join(f"{i['payer_name']} {spoken_amount(i['due_paise'], lang)}" for i in open_items[:MAX_NAMED])
    return f"{head} {named}."
