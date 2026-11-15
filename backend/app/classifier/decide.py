"""Decision procedure (DATA_AND_LOGIC 5.6), currently with the PLACEHOLDER score in place of the
model. Step 5 replaces placeholder.score with features + calibrated model + payer memory + rules 5a-5c.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .. import repo
from ..config import get_settings
from . import placeholder
from .threshold import current_model, effective_threshold

REASON_TEXT = {
    "CONFIGURED_FAMILY": "Marked as family by merchant",
    "FAMILY_NEEDS_CONFIRMATION": "Family money is only excluded after the merchant confirms",
    "P2P": "P2P transfer",
    "ROUND_AMOUNT": "Round amount",
}


@dataclass(frozen=True)
class Decision:
    suggested: str  # SALE | FAMILY
    confidence: float | None
    confidence_kind: str  # MODEL | NONE
    action: str  # AUTO_CLASSIFY | ASK_MERCHANT
    source: str  # MERCHANT_CONFIG | PAYER_MEMORY | MODEL | RULE
    reasons: list[str] = field(default_factory=list)
    q_model: float | None = None
    p_final: float | None = None
    model_version: str | None = None
    threshold: float = 0.9

    @property
    def classification(self) -> str:
        return self.suggested if self.action == "AUTO_CLASSIFY" else "PENDING"


def active_model_version() -> str:
    model = current_model()
    return model.model_version if model else placeholder.MODEL_VERSION


def threshold() -> float:
    model = current_model()
    return effective_threshold(model.threshold if model else None, get_settings().conf_threshold)


def decide(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    payer_id: str,
    payer_vpa_kind: str,
    amount_paise: int,
    payment_type: str,
    timestamp: str,
) -> Decision:
    tau = threshold()
    version = active_model_version()
    # Rule 1: the merchant's own instruction. Not a probability.
    if repo.is_family_payer(conn, merchant_id, payer_id):
        return Decision("FAMILY", None, "NONE", "AUTO_CLASSIFY", "MERCHANT_CONFIG",
                        [REASON_TEXT["CONFIGURED_FAMILY"]], None, None, version, tau)

    s = placeholder.score(payment_type=payment_type, payer_vpa_kind=payer_vpa_kind, amount_paise=amount_paise)
    if s.looks_family:
        reasons = [REASON_TEXT["FAMILY_NEEDS_CONFIRMATION"], REASON_TEXT["P2P"], REASON_TEXT["ROUND_AMOUNT"]]
        return Decision("FAMILY", round(s.q_model, 4), "MODEL", "ASK_MERCHANT", "RULE", reasons,
                        s.q_model, s.q_model, version, tau)
    confidence = round(1 - s.q_model, 4)
    return Decision("SALE", confidence, "MODEL", "AUTO_CLASSIFY", "MODEL", [], s.q_model, s.q_model, version, tau)
