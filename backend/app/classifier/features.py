"""Classifier features (DATA_AND_LOGIC 5.1). One builder for training, evaluation and the live API.

Features for a payment at time t use ONLY that merchant's payments strictly before t (ties broken by
transaction_id: earlier IDs only). No labels are used. Two ways to supply that history, which must
give identical vectors (tests/test_classifier.py checks this):
- MerchantHistory: incremental, for replaying a merchant's payments in (timestamp, transaction_id) order;
- history_from_db: the live API, from the payments table.
"""
from __future__ import annotations

import bisect
import math
import sqlite3
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .. import clock

CATEGORIES = ("VEGETABLES", "FRUITS", "FLOWERS", "TEA_STALL", "MIXED_KIRANA")
# "default category median if < 50 payments" (DATA 5.1), in rupees; same values as DATA 4.2
DEFAULT_MEDIAN_RUPEES = {"VEGETABLES": 120, "FRUITS": 180, "FLOWERS": 60, "TEA_STALL": 25, "MIXED_KIRANA": 150}
MIN_WINDOW_PAYMENTS = 50
WINDOW = timedelta(days=14)
NEW_PAYER_DAYS = 999.0

FEATURES = (
    "log_amount", "amt_ratio_median", "is_round_100", "is_round_500", "is_round_1000", "is_p2p",
    "is_business_vpa", "hour", "hour_sin", "hour_cos", "is_evening", "day_of_week", "is_sunday",
    "is_new_payer", "payer_prior_count", "payer_prior_p2p_share", "payer_amt_ratio", "days_since_payer_last",
    "payer_round_share", *(f"cat_{c}" for c in CATEGORIES),
)


@dataclass(frozen=True)
class Pay:
    transaction_id: str
    payer_id: str
    amount_paise: int
    payment_type: str
    payer_vpa_kind: str
    ts: datetime  # IST


@dataclass
class PayerStats:
    count: int = 0
    p2p: int = 0
    amount_sum: int = 0
    round100: int = 0
    last_ts: datetime | None = None


def median_of_sorted(values: list[int]) -> float:
    n = len(values)
    mid = n // 2
    return float(values[mid]) if n % 2 else (values[mid - 1] + values[mid]) / 2


def build(pay: Pay, category: str, window_sorted: list[int], payer: PayerStats) -> dict[str, float]:
    """window_sorted: amounts (paise) of the merchant's payments in [t - 14 days, t), sorted."""
    if len(window_sorted) >= MIN_WINDOW_PAYMENTS:
        median = median_of_sorted(window_sorted)
    else:
        median = DEFAULT_MEDIAN_RUPEES[category] * 100.0
    amount = pay.amount_paise
    hour = pay.ts.hour
    new = payer.count == 0
    f = {
        "log_amount": math.log(amount / 100),
        "amt_ratio_median": amount / median,
        "is_round_100": float(amount % 10_000 == 0),
        "is_round_500": float(amount % 50_000 == 0),
        "is_round_1000": float(amount % 100_000 == 0),
        "is_p2p": float(pay.payment_type == "P2P"),
        "is_business_vpa": float(pay.payer_vpa_kind == "BUSINESS"),
        "hour": float(hour),
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
        "is_evening": float(hour >= 18),
        "day_of_week": float(pay.ts.weekday()),
        "is_sunday": float(pay.ts.weekday() == 6),
        "is_new_payer": float(new),
        "payer_prior_count": float(payer.count),
        "payer_prior_p2p_share": 0.0 if new else payer.p2p / payer.count,
        "payer_amt_ratio": 1.0 if new else amount / (payer.amount_sum / payer.count),
        "days_since_payer_last": NEW_PAYER_DAYS if new else (pay.ts - payer.last_ts).total_seconds() / 86400,
        "payer_round_share": 0.0 if new else payer.round100 / payer.count,
    }
    for c in CATEGORIES:
        f[f"cat_{c}"] = float(category == c)
    return f


def vector(named: dict[str, float]) -> list[float]:
    return [named[name] for name in FEATURES]


# --- incremental history (training, evaluation, leakage tests) ----------------------------
@dataclass
class MerchantHistory:
    category: str
    _window: deque = field(default_factory=deque)  # (ts, amount) in processing order
    _sorted: list = field(default_factory=list)
    _payers: dict = field(default_factory=dict)

    def features(self, pay: Pay) -> dict[str, float]:
        """Features for pay from everything added so far. Call add(pay) afterwards."""
        cutoff = pay.ts - WINDOW
        while self._window and self._window[0][0] < cutoff:
            _, amount = self._window.popleft()
            del self._sorted[bisect.bisect_left(self._sorted, amount)]
        return build(pay, self.category, self._sorted, self._payers.get(pay.payer_id, PayerStats()))

    def add(self, pay: Pay) -> None:
        self._window.append((pay.ts, pay.amount_paise))
        bisect.insort(self._sorted, pay.amount_paise)
        s = self._payers.setdefault(pay.payer_id, PayerStats())
        s.count += 1
        s.p2p += pay.payment_type == "P2P"
        s.amount_sum += pay.amount_paise
        s.round100 += pay.amount_paise % 10_000 == 0
        s.last_ts = pay.ts


# --- live history from the database ---------------------------------------------------------
STRICTLY_BEFORE = "(timestamp < :t OR (timestamp = :t AND transaction_id < :txn))"
EARLIER_TIMESTAMP = "timestamp < :t"  # hypothetical payment (preview) has no transaction_id


def history_from_db(conn: sqlite3.Connection, merchant_id: str, pay: Pay, *,
                    hypothetical: bool = False) -> tuple[list[int], PayerStats]:
    """(sorted 14-day window amounts, payer stats) from payments strictly before pay."""
    t = clock.iso(pay.ts)
    cond = EARLIER_TIMESTAMP if hypothetical else STRICTLY_BEFORE
    params = {"m": merchant_id, "t": t, "txn": pay.transaction_id, "lo": clock.iso(pay.ts - WINDOW), "p": pay.payer_id}
    window = sorted(r[0] for r in conn.execute(
        f"SELECT amount_paise FROM payments WHERE merchant_id = :m AND timestamp >= :lo AND {cond}", params))
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(payment_type = 'P2P'), 0), COALESCE(SUM(amount_paise), 0),"
        " COALESCE(SUM(amount_paise % 10000 = 0), 0), MAX(timestamp)"
        f" FROM payments WHERE merchant_id = :m AND payer_id = :p AND {cond}", params,
    ).fetchone()
    stats = PayerStats(count=row[0], p2p=row[1], amount_sum=row[2], round100=row[3],
                       last_ts=clock.parse(row[4]) if row[4] else None)
    return window, stats
