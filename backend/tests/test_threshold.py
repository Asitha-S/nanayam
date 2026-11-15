"""Threshold watch (contract section 9): this financial year's business sales against the ₹40 lakh GST threshold for
goods. Business sales only (never total collections), from finance.summary.compute unchanged; fixed text by category."""
import json
from datetime import date

import pytest

from app.finance import threshold
from app.voice.answer import TEMPLATES_DIR

TA = json.loads((TEMPLATES_DIR / "ta.json").read_text(encoding="utf-8"))


def test_financial_year_runs_april_to_march():
    assert threshold.fy_start(date(2026, 11, 15)) == date(2026, 4, 1)
    assert threshold.fy_start(date(2026, 4, 1)) == date(2026, 4, 1)
    assert threshold.fy_start(date(2026, 3, 31)) == date(2025, 4, 1)
    assert threshold.fy_end(date(2026, 11, 15)) == date(2027, 3, 31)
    assert threshold.fy_end(date(2027, 1, 10)) == date(2027, 3, 31)


def test_m001_uses_business_sales_for_the_year_so_far(real):
    w = real.get("/api/merchants/M001/threshold-watch").json()
    s = real.get("/api/merchants/M001/summary?start_date=2026-04-01&end_date=2026-11-15").json()
    assert (w["start_date"], w["end_date"], w["fy_end_date"], w["financial_year"]) == ("2026-04-01", "2026-11-15", "2027-03-31", "2026-27")
    assert w["business_sales"]["amount_paise"] == s["business_sales"]["amount_paise"]
    assert w["total_collections"]["amount_paise"] == s["total_collections"]["amount_paise"]
    assert w["business_sales"]["amount_paise"] < w["total_collections"]["amount_paise"]  # family money is not a sale
    assert w["threshold"] == {"amount_paise": 400000000, "amount_display": "₹40,00,000",
                              "label": "GST registration threshold for goods"}
    sales = w["business_sales"]["amount_paise"]
    assert w["used_percent"] == round(sales * 100 / 400000000, 1)
    assert w["used_percent_display"] == f"{w['used_percent']:.1f}%"
    assert w["remaining"]["amount_paise"] == 400000000 - sales and w["crossed"] is False
    assert (w["days_remaining"], w["months_remaining"], w["months_remaining_display"]) == (136, 4.5, "4.5 months")
    assert w["business_sales"]["label"] == "Business sales this financial year"
    assert "not used for this limit" in w["total_collections"]["label"]


@pytest.mark.parametrize("merchant, kind", [("M001", "EXEMPT"), ("M002", "EXEMPT"), ("M003", "MIXED")])
def test_text_by_declared_category(real, merchant, kind):
    note = real.get(f"/api/merchants/{merchant}/threshold-watch").json()["note"]
    assert note["kind"] == kind
    assert note["en"] == threshold.NOTES_EN[kind]
    assert note["ta"] == TA[f"threshold_{kind.lower()}"]


def test_all_three_texts_exactly():
    assert threshold.note_for("FLOWERS")["en"] == ("You've declared tax-exempt goods. Sellers of only exempt goods usually "
                                                   "don't need GST registration. Confirm with a CA.")
    assert threshold.note_for("MIXED_KIRANA")["en"] == ("Exempt and taxable sales both count towards this limit. "
                                                        "Talk to a CA before you cross it.")
    tea = threshold.note_for("TEA_STALL")
    assert (tea["kind"], tea["en"], tea["ta"]) == ("TAXABLE", "Taxable sales. Talk to a CA before you cross it.",
                                                   TA["threshold_taxable"])
    assert threshold.note_for("SOMETHING_ELSE") == {"kind": None, "en": None, "ta": None, "te": None}
    assert all(TA[f"threshold_{k}"] for k in ("exempt", "mixed", "taxable"))


def test_pending_payments_are_noted_not_counted(real):
    from conftest import run_m001_demo

    run_m001_demo(real, answer=False)  # Lakshmi's ₹2,000 still waits for an answer
    w = real.get("/api/merchants/M001/threshold-watch").json()
    assert w["pending_note"] and "not counted" in w["pending_note"]


def test_unknown_merchant_is_404(real):
    assert real.get("/api/merchants/M999/threshold-watch").status_code == 404
