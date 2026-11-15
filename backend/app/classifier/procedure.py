"""Decision procedure (DATA_AND_LOGIC 5.6) and reasons (5.5). Pure functions: used by the live API,
by threshold and k selection in ml.train, and by the evaluation replay, so all three decide identically.

Order (agreed 2026-11-14): compute q_model for every payment first, then
  1  configured family   -> FAMILY, AUTO, MERCHANT_CONFIG          unless guardrail 5d -> ASK
  1b configured customer -> SALE,   AUTO, MERCHANT_CONFIG          unless its guardrail -> ASK
  2-4 model + payer memory + threshold
  5a-5c override rules (mixed payer, first-time large, family needs confirmation)
"""
from __future__ import annotations

from dataclasses import dataclass

K = 2  # default payer-memory prior weight (DATA 6); the trained artifact carries the selected k
FIRST_TIME_LARGE_PAISE = 500_000  # ₹5,000
FAMILY_GUARDRAIL_MAX_Q = 0.02  # 5d: configured family, P2M, not round to ₹100, q_model <= 0.02 -> ASK
CUSTOMER_GUARDRAIL_MIN_Q = 0.98  # 1b: configured customer, P2P, round to ₹500, q_model >= 0.98 -> ASK

REASON_TEXT = {  # priority order (DATA 5.5)
    "CONFIGURED_FAMILY": "Marked as family by merchant",
    "CONFIGURED_CUSTOMER": "Marked as customer by merchant",
    "FAMILY_GUARDRAIL": "Looks like a shop sale from a family payer",
    "CUSTOMER_GUARDRAIL": "Looks like family money from a customer",
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
    q_model: float
    p_final: float | None
    rules: tuple[str, ...]  # configuration / guardrail / override codes that decided

    @property
    def classification(self) -> str:
        return self.suggested if self.action == "AUTO_CLASSIFY" else "PENDING"


def memory_p(q: float, n_family: int, n_sale: int, k: float = K) -> float:
    n = n_family + n_sale
    return q if n == 0 else (k * q + n_family) / (k + n)


def family_guardrail(*, q: float, payment_type: str, amount_paise: int) -> bool:
    """5d: a configured family payer's payment that looks like a shop sale."""
    return payment_type == "P2M" and amount_paise % 10_000 != 0 and q <= FAMILY_GUARDRAIL_MAX_Q


def customer_guardrail(*, q: float, payment_type: str, amount_paise: int) -> bool:
    """1b guardrail: a configured customer's payment that looks like family money."""
    return payment_type == "P2P" and amount_paise % 50_000 == 0 and q >= CUSTOMER_GUARDRAIL_MIN_Q


def _model_ask(q: float, rule: str) -> Outcome:
    suggested = "FAMILY" if q >= 0.5 else "SALE"
    return Outcome(suggested, max(q, 1 - q), "MODEL", "ASK_MERCHANT", "RULE", q, q, (rule,))


def run(*, q: float, n_family: int, n_sale: int, is_new_payer: bool, amount_paise: int, payment_type: str,
        tau: float, configured_family: bool = False, configured_customer: bool = False, k: float = K) -> Outcome:
    # 1. The merchant's own instruction (not a probability), with its guardrail.
    if configured_family:
        if family_guardrail(q=q, payment_type=payment_type, amount_paise=amount_paise):
            return _model_ask(q, "FAMILY_GUARDRAIL")
        return Outcome("FAMILY", None, "NONE", "AUTO_CLASSIFY", "MERCHANT_CONFIG", q, None, ("CONFIGURED_FAMILY",))
    # 1b. Remembered customer, with its guardrail.
    if configured_customer:
        if customer_guardrail(q=q, payment_type=payment_type, amount_paise=amount_paise):
            return _model_ask(q, "CUSTOMER_GUARDRAIL")
        return Outcome("SALE", None, "NONE", "AUTO_CLASSIFY", "MERCHANT_CONFIG", q, None, ("CONFIGURED_CUSTOMER",))
    # 2-4. Model, payer memory, threshold.
    n = n_family + n_sale
    p = memory_p(q, n_family, n_sale, k)
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
