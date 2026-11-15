"""PLACEHOLDER CLASSIFIER. NOT A MODEL. MUST BE REPLACED BY THE TRAINED MODEL (build step 5). NEVER SHIP.

Exists only so the 14:00 integration is not blocked by model training:
P2P + PERSONAL + amount a multiple of ₹500  -> suggest FAMILY, ask the merchant
everything else                              -> SALE, auto-classified
/health and every prediction row report MODEL_VERSION below, so it is visible wherever it is active.
"""
from __future__ import annotations

from dataclasses import dataclass

MODEL_VERSION = "placeholder-rule-not-a-model"


@dataclass(frozen=True)
class PlaceholderScore:
    q_model: float  # stand-in for calibrated p(FAMILY)
    looks_family: bool


def score(*, payment_type: str, payer_vpa_kind: str, amount_paise: int) -> PlaceholderScore:
    looks_family = payment_type == "P2P" and payer_vpa_kind == "PERSONAL" and amount_paise % 50_000 == 0
    return PlaceholderScore(q_model=0.6 if looks_family else 0.02, looks_family=looks_family)
