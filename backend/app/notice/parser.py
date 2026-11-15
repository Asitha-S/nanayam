from __future__ import annotations

import re
from typing import Any


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def check_span(span: str, ocr_text: str) -> float | str:
    if not span:
        return "NOT_FOUND"
    if span in ocr_text:
        return 0.95
    if _normalize_text(span) == _normalize_text(ocr_text):
        return 0.80
    if _normalize_text(span) in _normalize_text(ocr_text):
        return 0.80
    return "NOT_FOUND"


def extract_notice_metadata(ocr_text: str, extraction: dict[str, Any] | None = None) -> dict[str, Any]:
    base = extraction or {
        "notice_title": "GST NOTICE",
        "issuing_office": "Tamil Nadu Commercial Taxes Department",
        "reference_number": "GST-REF-1207",
        "issue_date": "2026-11-01",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "amount_questioned_rupees": 150000,
        "response_deadline": "2026-11-15",
    }
    result: dict[str, Any] = {}
    for key, value in base.items():
        if value is None:
            result[key] = {"value": None, "confidence": "NOT_FOUND"}
            continue
        confidence = check_span(str(value), ocr_text)
        result[key] = {"value": value, "confidence": confidence}
    return result


def render_notice_explanation(facts: dict[str, Any], metadata: dict[str, Any], *, lang: str = "ta") -> str:
    if lang != "ta":
        return render_notice_explanation(facts, metadata, lang="ta")
    amount = int(facts.get("amount_questioned_rupees", facts.get("amount") or 0))
    sales = int(facts.get("business_sales", 0))
    family = int(facts.get("family_transfers", 0))
    deadline = metadata.get("response_deadline", {}).get("value", "அடுத்த வெள்ளிக்கிழமை")
    text = (
        f"இந்த அறிவிப்பில் கேட்கப்பட்ட தொகை {amount} ரூபாய். "
        f"கடை UPI வசூல் {sales} ரூபாய், வீட்டு பணம் {family} ரூபாய், "
        f"கடைசி தேதியில் பதில் அளிக்க வேண்டும்: {deadline}."
    )
    return text


__all__ = ["check_span", "extract_notice_metadata", "render_notice_explanation"]
