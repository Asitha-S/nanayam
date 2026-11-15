"""Decision procedure (DATA_AND_LOGIC 5.6) and reasons (5.5). Pure functions: used by the live API,
by threshold selection in ml.train, and by the evaluation replay, so all three decide identically.
"""
from __future__ import annotations

from dataclasses import dataclass

K = 2  # payer-memory prior weight (DATA 6)
FIRST_TIME_LARGE_PAISE = 500_000  # ₹5,000

REASON_TEXT = {  # priority order (DATA 5.5)
    "CONFIGURED_FAMILY": "Marked as family by merchant",
    "MIXED_PAYER": "This person has paid for both shop and family before",
    "FIRST_TIME_LARGE": "First payment from this person, and large",
    "FAMILY_NEEDS_CONFIRMATION": "Family money is only excluded after the merchant confirms",
    "PAYER_CONFIRMED_FAMILY": "Merchant confirmed this person's money as family before",
    "PAYER_CONFIRMED_SALE": "Merchant confirmed this person's payments as sales before",
    "NEW_PAYER": "New payer",
    "P2P": "P2P transfer",
    "ROUND_AMOUNT": "Round amount",
    "LARGER_THAN_USUAL": "Larger than usual sale",
    "BUSINESS_VPA": "Business UPI ID",
    "REGULAR_CUSTOMER": "Regular customer",
    "TYPICAL_AMOUNT": "Typical sale amount",
}
MAX_REASONS = 4


@dataclass(frozen=True)
class Outcome:
    suggested: str  # SALE | FAMILY
    confidence: float | None  # max(p, 1-p); None for MERCHANT_CONFIG
    confidence_kind: str  # MODEL | NONE
    action: str  # AUTO_CLASSIFY | ASK_MERCHANT
    source: str  # MERCHANT_CONFIG | PAYER_MEMORY | MODEL | RULE
    q_model: float | None
    p_final: float | None
    rules: tuple[str, ...]  # override rules that fired

    @property
    def classification(self) -> str:
        return self.suggested if self.action == "AUTO_CLASSIFY" else "PENDING"


def memory_p(q: float, n_family: int, n_sale: int, k: int = K) -> float:
    n = n_family + n_sale
    return q if n == 0 else (k * q + n_family) / (k + n)


def run(*, q: float | None, n_family: int, n_sale: int, configured: bool, is_new_payer: bool, amount_paise: int,
        tau: float) -> Outcome:
    # 1. The merchant's own instruction: not a probability.
    if configured:
        return Outcome("FAMILY", None, "NONE", "AUTO_CLASSIFY", "MERCHANT_CONFIG", None, None, ("CONFIGURED_FAMILY",))
    assert q is not None
    # 2-4. Model, payer memory, threshold.
    n = n_family + n_sale
    p = memory_p(q, n_family, n_sale)
    source = "PAYER_MEMORY" if n > 0 else "MODEL"
    suggested = "FAMILY" if p >= 0.5 else "SALE"
    confidence = max(p, 1 - p)
    action = "AUTO_CLASSIFY" if confidence >= tau else "ASK_MERCHANT"
    # 5. Overrides: force ASK, keep suggestion and confidence.
    rules = []
    if n >= 3 and min(n_family, n_sale) / n >= 0.25:
        rules.append("MIXED_PAYER")  # 5a
    if is_new_payer and amount_paise >= FIRST_TIME_LARGE_PAISE:
        rules.append("FIRST_TIME_LARGE")  # 5b
    if suggested == "FAMILY" and n_family == 0:
        rules.append("FAMILY_NEEDS_CONFIRMATION")  # 5c: never exclude income silently for an unconfirmed payer
    if rules:
        action, source = "ASK_MERCHANT", "RULE"
    return Outcome(suggested, confidence, "MODEL", action, source, q, p, tuple(rules))


def reasons(outcome: Outcome, features: dict[str, float] | None, n_family: int, n_sale: int) -> list[str]:
    """Up to 4 short signals in priority order. They describe inputs; they do not explain the model."""
    codes = list(outcome.rules)
    if outcome.source != "MERCHANT_CONFIG" and features is not None:
        if n_family > 0:
            codes.append("PAYER_CONFIRMED_FAMILY")
        if n_sale > 0:
            codes.append("PAYER_CONFIRMED_SALE")
        if features["is_new_payer"]:
            codes.append("NEW_PAYER")
        if features["is_p2p"]:
            codes.append("P2P")
        if features["is_round_100"]:
            codes.append("ROUND_AMOUNT")
        if features["amt_ratio_median"] >= 5:
            codes.append("LARGER_THAN_USUAL")
        if features["is_business_vpa"]:
            codes.append("BUSINESS_VPA")
        if features["payer_prior_count"] >= 5 and features["payer_prior_p2p_share"] < 0.5:
            codes.append("REGULAR_CUSTOMER")
        if 0.3 <= features["amt_ratio_median"] <= 3:
            codes.append("TYPICAL_AMOUNT")
    order = list(REASON_TEXT)
    codes = sorted(dict.fromkeys(codes), key=order.index)
    return [REASON_TEXT[c] for c in codes[:MAX_REASONS]]
