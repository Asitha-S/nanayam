"""Threshold watch (contract section 9, added 2026-11-15): this financial year's business sales against the ₹40 lakh GST
registration threshold for goods. Owner: Asitha.

Read-only. Business sales come from finance.summary.compute for 1 April to today, unchanged; total UPI collections are
shown beside them for contrast but never used for the limit. The text by declared category is fixed (English here,
Tamil from templates/ta.json); no LLM. Not tax advice: every line sends the merchant to a CA.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from functools import lru_cache

from .. import clock, money, repo
from ..voice.answer import TEMPLATES_DIR
from . import summary

THRESHOLD_PAISE = 40_00_000 * 100  # ₹40 lakh: GST registration threshold for suppliers of goods
DAYS_PER_MONTH = 365.25 / 12

NOTE_KIND = {"VEGETABLES": "EXEMPT", "FRUITS": "EXEMPT", "FLOWERS": "EXEMPT", "MIXED_KIRANA": "MIXED", "TEA_STALL": "TAXABLE"}
NOTES_EN = {
    "EXEMPT": "You've declared tax-exempt goods. Sellers of only exempt goods usually don't need GST registration. "
              "Confirm with a CA.",
    "MIXED": "Exempt and taxable sales both count towards this limit. Talk to a CA before you cross it.",
    "TAXABLE": "Taxable sales. Talk to a CA before you cross it.",
}
TEMPLATE_KEYS = {"EXEMPT": "threshold_exempt", "MIXED": "threshold_mixed", "TAXABLE": "threshold_taxable"}


def fy_start(d: date) -> date:
    """1 April of the financial year that d falls in (Indian FY: April to March)."""
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def fy_end(d: date) -> date:
    return date(fy_start(d).year + 1, 3, 31)


@lru_cache
def _template(lang: str) -> dict:
    path = TEMPLATES_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def note_for(category: str | None) -> dict:
    """{kind, en, ta, te} for a declared category; kind None (no text) for a category without a rule."""
    kind = NOTE_KIND.get(category or "")
    if kind is None:
        return {"kind": None, "en": None, "ta": None, "te": None}
    key = TEMPLATE_KEYS[kind]
    return {"kind": kind, "en": NOTES_EN[kind], "ta": _template("ta").get(key), "te": _template("te").get(key)}


def watch(conn: sqlite3.Connection, merchant_id: str) -> dict:
    m = repo.require_merchant(conn, merchant_id)
    today = clock.today()
    start, end = fy_start(today), fy_end(today)
    b = summary.compute(conn, merchant_id, start, today)
    used = round(b.business_sales * 100 / THRESHOLD_PAISE, 1)
    remaining = max(0, THRESHOLD_PAISE - b.business_sales)
    days_left = (end - today).days
    months_left = round(days_left / DAYS_PER_MONTH, 1)
    return {
        "merchant_id": merchant_id,
        "as_of": clock.iso(clock.now()),
        "financial_year": f"{start.year}-{str(start.year + 1)[2:]}",
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "fy_end_date": end.isoformat(),
        "business_sales": {"amount_paise": b.business_sales, "amount_display": money.display(b.business_sales),
                           "label": "Business sales this financial year"},
        "total_collections": {"amount_paise": b.total_collections, "amount_display": money.display(b.total_collections),
                              "label": "All UPI money received (not used for this limit)"},
        "threshold": {"amount_paise": THRESHOLD_PAISE, "amount_display": money.display(THRESHOLD_PAISE),
                      "label": "GST registration threshold for goods"},
        "used_percent": used,
        "used_percent_display": f"{used:.1f}%",
        "remaining": {"amount_paise": remaining, "amount_display": money.display(remaining)},
        "crossed": b.business_sales >= THRESHOLD_PAISE,
        "days_remaining": days_left,
        "months_remaining": months_left,
        "months_remaining_display": f"{months_left:.1f} months",
        "business_category": m["business_category"],
        "note": note_for(m["business_category"]),
        "pending_note": "Payments still waiting for an answer are not counted until they're answered."
                        if b.pending else None,
    }
