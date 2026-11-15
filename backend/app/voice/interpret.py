from __future__ import annotations

import json
import re
from typing import Any

from .. import errors
from ..sarvam import client as sarvam
from .utils import parse_amount

INTENT_VALUES = ("LOG_EXPENSE", "ASK_DAILY_PROFIT", "CONFIRM_TRANSACTION", "UNKNOWN")
CATEGORY_VALUES = ("STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT", "WAGES", "UTILITIES", "OTHER")
CONFIRMED_VALUES = ("SALE", "FAMILY")


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _parse_json_payload(content: str) -> dict[str, Any]:
    if not content:
        raise ValueError("Empty LLM response")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("JSON content was not an object")
    return data


def _rule_based_fallback(transcript: str, *, open_question_id: str | None = None) -> dict[str, Any]:
    text = transcript.casefold()
    amount_match = re.search(r"(\d[\d,\s]*\d|[a-zA-Z\u0B80-\u0BFF]+(?:\s+[a-zA-Z\u0B80-\u0BFF]+)*)", text)
    amount_span = amount_match.group(0) if amount_match else ""
    amount_rupees = parse_amount(amount_span) if amount_span else 0

    intent = "UNKNOWN"
    category = None
    confirmed_category = None
    remember_payer = False
    description = ""
    day = None

    if open_question_id:
        if any(token in text for token in ["வீட்டு", "family", "family money", "வீட்டுப்பணம்", "home", "வீட்டு பணம்"]):
            intent = "CONFIRM_TRANSACTION"
            confirmed_category = "FAMILY"
        elif any(token in text for token in ["கடை", "sale", "வியாபாரம்", "shop", "business"]):
            intent = "CONFIRM_TRANSACTION"
            confirmed_category = "SALE"

    if intent == "UNKNOWN" and any(token in text for token in ["லாபம்", "labham", "meedham", "profit", "மீதம்", "கணக்கு"]):
        intent = "ASK_DAILY_PROFIT"
        day = "today"
    elif intent == "UNKNOWN" and any(token in text for token in ["வாங்கி", "வாங்கினேன்", "செலவு", "kharchu", "கொடுத்தேன்", "கொன்னேன்", "கோயம்பேடு", "vaangi", "khaarchu"]):
        intent = "LOG_EXPENSE"
        category = "STOCK_PURCHASE"
        description = "காய்கறி" if "காய்கறி" in text or "kaaikari" in text else "செலவு"
    elif intent == "UNKNOWN" and amount_span and not any(token in text for token in ["லாபம்", "செலவு", "வாங்க", "பணம்"]):
        intent = "UNKNOWN"

    if intent == "LOG_EXPENSE" and amount_span:
        amount_rupees = parse_amount(amount_span)
        if amount_rupees < 1:
            intent = "UNKNOWN"

    result = {
        "intent": intent,
        "amount_rupees": amount_rupees,
        "amount_text_span": amount_span,
        "category": category,
        "description": description,
        "day": day,
        "confirmed_category": confirmed_category,
        "remember_payer": remember_payer,
        "status": "FALLBACK_USED",
    }
    return result


def _validate_response(payload: dict[str, Any], transcript: str) -> tuple[bool, str]:
    intent = payload.get("intent")
    if intent not in INTENT_VALUES:
        return False, "invalid intent"

    amount_rupees = payload.get("amount_rupees")
    amount_span = payload.get("amount_text_span")
    if amount_span is None:
        return False, "missing amount span"
    if not isinstance(amount_rupees, int):
        return False, "amount_rupees is not int"
    if not isinstance(amount_span, str):
        return False, "amount_text_span is not string"

    text = _normalize_text(transcript)
    span = _normalize_text(amount_span)
    if not span or span not in text and re.sub(r"\s+", "", span) not in re.sub(r"\s+", "", text):
        return False, "amount span missing from transcript"

    try:
        parsed = parse_amount(amount_span)
    except ValueError:
        return False, "unparseable amount span"

    if parsed != amount_rupees:
        return False, "amount mismatch"

    if not (1 <= amount_rupees <= 500_000):
        return False, "amount out of range"

    category = payload.get("category")
    if category is not None and category not in CATEGORY_VALUES:
        return False, "category invalid"

    confirmed_category = payload.get("confirmed_category")
    if confirmed_category is not None and confirmed_category not in CONFIRMED_VALUES:
        return False, "confirmed_category invalid"

    if payload.get("remember_payer") is not None and not isinstance(payload.get("remember_payer"), bool):
        return False, "remember_payer type invalid"

    return True, "ok"


def interpret_utterance(
    transcript: str,
    *,
    language: str = "ta",
    merchant_id: str | None = None,
    open_question_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Interpret speech and return structured output with deterministic validation.

    Returns a dict containing the LLM output plus status. The status is one of:
      SUCCESS, NEEDS_CLARIFICATION, FALLBACK_USED.
    """
    if not transcript or not transcript.strip():
        raise ValueError("Transcript is required")

    messages = [
        {
            "role": "system",
            "content": (
                "Return only valid JSON matching the schema: {intent, amount_rupees, amount_text_span, category, "
                "description, day, confirmed_category, remember_payer}. Use temperature 0."
            ),
        },
        {"role": "user", "content": transcript},
    ]

    schema = {
        "type": "object",
        "properties": {
            "intent": {"enum": ["LOG_EXPENSE", "ASK_DAILY_PROFIT", "CONFIRM_TRANSACTION", "UNKNOWN"]},
            "amount_rupees": {"type": "integer"},
            "amount_text_span": {"type": "string"},
            "category": {"enum": ["STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT", "WAGES", "UTILITIES", "OTHER", None]},
            "description": {"type": "string"},
            "day": {"enum": ["today", "yesterday", None]},
            "confirmed_category": {"enum": ["SALE", "FAMILY", None]},
            "remember_payer": {"type": "boolean"},
        },
        "required": ["intent", "amount_rupees", "amount_text_span", "category", "description", "day", "confirmed_category", "remember_payer"],
    }

    try:
        result = sarvam.chat(messages, schema=schema)
        payload = _parse_json_payload(result.content)
        ok, reason = _validate_response(payload, transcript)
        if ok:
            payload["status"] = "SUCCESS"
            return payload
        raise ValueError(reason)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        fallback = _rule_based_fallback(transcript, open_question_id=open_question_id)
        fallback["status"] = "FALLBACK_USED"
        return fallback
    except Exception:
        fallback = _rule_based_fallback(transcript, open_question_id=open_question_id)
        fallback["status"] = "NEEDS_CLARIFICATION"
        return fallback


__all__ = ["interpret_utterance", "_rule_based_fallback", "_validate_response"]
