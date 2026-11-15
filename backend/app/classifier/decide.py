"""Live decision for one payment (DATA_AND_LOGIC 5.6): merchant config, features from strictly earlier
payments, calibrated model, payer memory, override rules 5a-5c, reasons.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .. import clock, repo
from ..config import get_settings
from ..feedback.memory import payer_counts
from . import features, model, procedure
from .threshold import current_model, effective_threshold


@dataclass(frozen=True)
class Decision:
    suggested: str  # SALE | FAMILY
    confidence: float | None  # 4 dp; None for MERCHANT_CONFIG
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


def active_model_version() -> str | None:
    info = current_model()
    return info.model_version if info else None


def threshold() -> float:
    info = current_model()
    return effective_threshold(info.threshold if info else None, get_settings().conf_threshold)


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def decide(
    conn: sqlite3.Connection,
    *,
    merchant_id: str,
    payer_id: str,
    payer_vpa_kind: str,
    amount_paise: int,
    payment_type: str,
    timestamp: str,
    transaction_id: str | None = None,
) -> Decision:
    """transaction_id None = hypothetical payment (preview): history is every payment before timestamp."""
    tau = threshold()
    version = active_model_version()
    if repo.is_family_payer(conn, merchant_id, payer_id):
        out = procedure.run(q=None, n_family=0, n_sale=0, configured=True, is_new_payer=False,
                            amount_paise=amount_paise, tau=tau)
        return Decision(out.suggested, None, "NONE", out.action, out.source,
                        procedure.reasons(out, None, 0, 0), None, None, version, tau)

    category = repo.merchant(conn, merchant_id)["business_category"]
    pay = features.Pay(transaction_id or "", payer_id, amount_paise, payment_type, payer_vpa_kind,
                       clock.parse(timestamp))
    window, stats = features.history_from_db(conn, merchant_id, pay, hypothetical=transaction_id is None)
    named = features.build(pay, category, window, stats)
    q = model.q_model(features.vector(named))
    n_family, n_sale = payer_counts(conn, merchant_id, payer_id)
    out = procedure.run(q=q, n_family=n_family, n_sale=n_sale, configured=False,
                        is_new_payer=bool(named["is_new_payer"]), amount_paise=amount_paise, tau=tau)
    return Decision(out.suggested, _round(out.confidence), out.confidence_kind, out.action, out.source,
                    procedure.reasons(out, named, n_family, n_sale), _round(out.q_model), _round(out.p_final),
                    version, tau)
