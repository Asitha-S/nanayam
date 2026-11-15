"""Synthetic merchants, payers, payments, refunds, reversals, expenses and ground-truth labels
(DATA_AND_LOGIC section 4). Deterministic for a given seed. Ground truth is never read by the backend.

Payer IDs:
- demo merchants (M001-M003): customers P10001-P19999 (one shared counter, M001's 12 named demo
  customers reserved), business buyers P2xxxx, family/friends P9xxxx;
- evaluation merchants (M101-M140): P{merchant number}{nnnnn}, e.g. P10100042.
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

import numpy as np
import pandas as pd

from . import params as P
from .names import BUSINESS_NAMES, CUSTOMER_REASONS_REFUND, FIRST_NAMES, INITIALS, SURNAMES

IST = timezone(timedelta(hours=5, minutes=30), "IST")
DAYS = [P.START + timedelta(days=i) for i in range((P.END - P.START).days + 1)]
PERIOD_END = datetime.combine(P.END, P.SHOP_CLOSE, tzinfo=IST)

DEMO_MERCHANTS = [
    {"merchant_id": "M001", "display_name": "Murugan Kaaikari Kadai", "owner_name": "Murugan",
     "business_category": "VEGETABLES", "preferred_language": "ta"},
    {"merchant_id": "M002", "display_name": "Venkatesh Pandla Dukanam", "owner_name": "Venkatesh",
     "business_category": "FRUITS", "preferred_language": "te"},
    {"merchant_id": "M003", "display_name": "Ravi Stores", "owner_name": "Ravi",
     "business_category": "MIXED_KIRANA", "preferred_language": "ta"},
]

# DATA_AND_LOGIC 3.2 named payers: id -> (name, vpa kind)
NAMED_PAYERS = {
    "P20001": ("Anbu Mess", "BUSINESS"),
    "P90001": ("Lakshmi R", "PERSONAL"),  # no history; first payment on demo day
    "P90002": ("Karthik", "PERSONAL"),
    "P90003": ("Selvi", "PERSONAL"),
    "P20011": ("Hotel Sri Sai", "BUSINESS"),
    "P90011": ("Srinivas", "PERSONAL"),  # no history; first payment on demo day
    "P90004": ("Mani", "PERSONAL"),
    "P90005": ("Jaya", "PERSONAL"),
    "P90006": ("Prabhu", "PERSONAL"),
}

# M001 demo-day customers (DATA 3.3), names as in contract/fixtures. Must be existing regulars.
M001_DEMO_CUSTOMERS = [
    ("P10411", "Senthil K"), ("P10057", "Revathi"), ("P10233", "Arun Kumar"), ("P10019", "Meena S"),
    ("P10388", "Prakash"), ("P10102", "Divya R"), ("P10276", "Gopal"), ("P10040", "Kavitha"),
    ("P10345", "Ramesh"), ("P10150", "Saranya"), ("P10077", "Vijay"), ("P10012", "Bala"),
]
M001_DEMO_RANKS = [0, 1, 2, 3, 4, 6, 8, 10, 13, 16, 20, 24]  # Zipf ranks (0 = most frequent)

# Three M001 payments left unanswered in the seed history (agreed 2026-11-14).
FIXED_UNANSWERED = [
    ("P90004", date(2026, 10, 29), 3000),
    ("P90005", date(2026, 10, 30), 1000),
    ("P90006", date(2026, 10, 31), 1500),
]
FIXED_UNANSWERED_TIME = time(20, 5)

# Selvi: mixed payer, 2 sales (non-round P2M) and 3 family transfers (round P2P).
SELVI_SCHEDULE = [
    (date(2026, 8, 20), time(19, 32, 40), 100000, "P2P", "FAMILY"),
    (date(2026, 9, 6), time(8, 14, 5), 34700, "P2M", "SALE"),
    (date(2026, 9, 25), time(20, 11, 12), 200000, "P2P", "FAMILY"),
    (date(2026, 10, 12), time(7, 48, 51), 26800, "P2M", "SALE"),
    (date(2026, 10, 27), time(19, 46, 3), 150000, "P2P", "FAMILY"),
]

FAMILY_CONFIG = [  # merchant configuration at setup
    {"merchant_id": "M001", "payer_id": "P90002", "relation_label": "Thambi (brother)",
     "added_at": P.MERCHANT_CREATED_AT, "added_via": "SETUP"},
]

EXPENSE_TEXT = {
    "M001": {"STOCK_PURCHASE": "Kaaikari, Koyambedu", "TRANSPORT": "Auto, Koyambedu", "PACKAGING": "Cover",
             "RENT": "Kadai vaadagai"},
    "M002": {"STOCK_PURCHASE": "Pandlu, Koyambedu", "TRANSPORT": "Auto", "PACKAGING": "Cover", "RENT": "Kottu adde"},
    "M003": {"STOCK_PURCHASE": "Sarakku, wholesale", "TRANSPORT": "Lorry", "PACKAGING": "Pai", "RENT": "Kadai vaadagai"},
}
STOCK_RANGE = {"VEGETABLES": (2500, 4500), "FRUITS": (3000, 5500), "MIXED_KIRANA": (8000, 20000)}


# --- small helpers ------------------------------------------------------------
def _slot_weights() -> tuple[np.ndarray, int]:
    open_min = P.SHOP_OPEN.hour * 60 + P.SHOP_OPEN.minute
    close_min = P.SHOP_CLOSE.hour * 60 + P.SHOP_CLOSE.minute
    starts = list(range(open_min, close_min, 30))
    w = []
    for s in starts:
        peak = any(a.hour * 60 + a.minute <= s < b.hour * 60 + b.minute for a, b in P.PEAKS)
        w.append(P.PEAK_WEIGHT if peak else 1.0)
    w = np.array(w)
    return w / w.sum(), open_min * 60


SLOT_P, OPEN_SEC = _slot_weights()


def shop_seconds(rng, n: int) -> np.ndarray:
    slots = rng.choice(len(SLOT_P), size=n, p=SLOT_P)
    return OPEN_SEC + slots * 1800 + rng.integers(0, 1800, size=n)


def window_seconds(rng, n: int, start: time, end: time) -> np.ndarray:
    a = start.hour * 3600 + start.minute * 60
    b = end.hour * 3600 + end.minute * 60
    return rng.integers(a, b, size=n)


def at(day: date, seconds: int) -> datetime:
    return datetime.combine(day, time(0), tzinfo=IST) + timedelta(seconds=int(seconds))


def customer_rupees(rng, category: str, n: int) -> np.ndarray:
    c = P.CATEGORY[category]
    x = c["median"] * np.exp(c["sigma"] * rng.standard_normal(n))
    r = np.rint(x).astype(np.int64)
    round5 = rng.random(n) < P.ROUND_TO_5
    r[round5] = (np.rint(r[round5] / 5) * 5).astype(np.int64)
    return np.clip(r, c["lo"], c["hi"])


def person_name(rng) -> str:
    return f"{rng.choice(FIRST_NAMES)}{rng.choice(INITIALS)}{rng.choice(SURNAMES) if rng.random() < 0.2 else ''}"


def make_uuid(rng) -> str:
    return str(uuid.UUID(bytes=rng.bytes(16), version=4))


# --- ID allocation ------------------------------------------------------------
class DemoIds:
    """Shared ID counters for M001-M003."""

    def __init__(self):
        self.reserved = {pid for pid, _ in M001_DEMO_CUSTOMERS} | set(NAMED_PAYERS)
        self.counters = {"customer": 10001, "business": 20021, "family": 90101}
        self.limits = {"customer": 19999, "business": 29999, "family": 99999}

    def take(self, kind: str) -> str:
        while f"P{self.counters[kind]}" in self.reserved:
            self.counters[kind] += 1
        n = self.counters[kind]
        if n > self.limits[kind]:
            raise RuntimeError(f"demo payer id range exhausted for {kind}")
        self.counters[kind] += 1
        return f"P{n}"


class EvalIds:
    def __init__(self, merchant_id: str):
        self.prefix = f"P{merchant_id[1:]}"
        self.n = 0

    def take(self, kind: str) -> str:
        self.n += 1
        return f"{self.prefix}{self.n:05d}"


# --- result ---------------------------------------------------------------------
@dataclass
class Generated:
    merchants: pd.DataFrame
    payers: pd.DataFrame
    payments: pd.DataFrame
    refunds: pd.DataFrame
    reversals: pd.DataFrame
    expenses: pd.DataFrame
    labels: pd.DataFrame
    family_config: pd.DataFrame
    regular_pools: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class _Ctx:
    merchant: dict
    rng: np.random.Generator
    ids: object
    payers: dict  # payer_id -> (name, kind)
    rows: list  # payment dicts (no transaction_id yet)
    family_rate: float = 1.0  # robustness only: family/friend transfer rate multiplier (1.0 = as specified)
    specs: list = field(default_factory=list)  # (kind, payer_id, kwargs) of family/friend payers, for rescaling

    def payer(self, pid: str, name: str, kind: str) -> str:
        if pid in self.payers and self.payers[pid] != (name, kind):
            raise RuntimeError(f"payer {pid} defined twice differently")
        self.payers[pid] = (name, kind)
        return pid

    def pay(self, pid, ts, rupees_or_paise, ptype, label, role, *, paise=False, protected=False):
        name, kind = self.payers[pid]
        self.rows.append({
            "merchant_id": self.merchant["merchant_id"], "payer_id": pid, "payer_name": name,
            "payer_vpa_kind": kind, "amount_paise": int(rupees_or_paise if paise else rupees_or_paise * 100),
            "payment_type": ptype, "ts": ts, "description": None,
            "true_label": label, "payer_role": role, "protected": protected,
        })


# --- roles ----------------------------------------------------------------------
def _customers(ctx: _Ctx, scale: float, pool: list[str]) -> None:
    rng, cat = ctx.rng, ctx.merchant["business_category"]
    lam = P.CATEGORY[cat]["lam"] * scale
    ranks = np.arange(1, len(pool) + 1, dtype=float)
    zipf_p = ranks ** -P.ZIPF_S
    zipf_p /= zipf_p.sum()
    for day in DAYS:
        n = rng.poisson(lam * (P.SUNDAY_FACTOR if day.weekday() == 6 else 1.0))
        if n == 0:
            continue
        walk = rng.random(n) < P.WALKIN_SHARE
        picks = rng.choice(len(pool), size=n, p=zipf_p)
        p2m = rng.random(n) < P.CUSTOMER_P2M
        amounts = customer_rupees(rng, cat, n)
        secs = shop_seconds(rng, n)
        big = rng.random(n) < P.REGULAR_BIG_ORDER_SHARE
        for i in range(n):
            ptype, rupees = ("P2M" if p2m[i] else "P2P"), int(amounts[i])
            if walk[i]:
                kind = "PERSONAL" if rng.random() < P.CUSTOMER_PERSONAL else "BUSINESS"
                pid = ctx.payer(ctx.ids.take("customer"), person_name(rng), kind)
                role = "walk_in"
            else:
                pid, role = pool[picks[i]], "regular_customer"
                if big[i]:  # paying for a bigger order by P2P, round amount
                    ptype, rupees = "P2P", int(round(rng.uniform(*P.REGULAR_BIG_ORDER_AMOUNT) / 100) * 100)
            ctx.pay(pid, at(day, secs[i]), rupees, ptype, "SALE", role)


def _regular_pool(ctx: _Ctx) -> list[str]:
    rng = ctx.rng
    pool: list[str | None] = [None] * P.REGULAR_POOL
    if ctx.merchant["merchant_id"] == "M001":
        for (pid, name), rank in zip(M001_DEMO_CUSTOMERS, M001_DEMO_RANKS):
            pool[rank] = ctx.payer(pid, name, "PERSONAL")
    for i in range(P.REGULAR_POOL):
        if pool[i] is None:
            kind = "PERSONAL" if rng.random() < P.CUSTOMER_PERSONAL else "BUSINESS"
            pool[i] = ctx.payer(ctx.ids.take("customer"), person_name(rng), kind)
    return pool  # type: ignore[return-value]


def _business_buyer(ctx: _Ctx, pid: str, amount=P.BUSINESS_AMOUNT, p2m=P.BUSINESS_P2M) -> None:
    rng = ctx.rng
    d = int(rng.integers(0, 3))
    while d < len(DAYS):
        rupees = int(round(rng.uniform(*amount) / 10) * 10)
        ptype = "P2M" if rng.random() < p2m else "P2P"
        ctx.pay(pid, at(DAYS[d], shop_seconds(rng, 1)[0]), rupees, ptype, "SALE", "business_buyer")
        d += int(rng.integers(P.BUSINESS_GAP_DAYS[0], P.BUSINESS_GAP_DAYS[1] + 1))


def _big_orders(ctx: _Ctx) -> None:
    rng = ctx.rng
    for day in DAYS:
        if rng.random() >= 1 / P.BIG_ORDER_EVERY_DAYS:
            continue
        kind = "PERSONAL" if rng.random() < P.CUSTOMER_PERSONAL else "BUSINESS"
        pid = ctx.payer(ctx.ids.take("customer"), person_name(rng), kind)
        rupees = rng.uniform(*P.BIG_ORDER_AMOUNT)
        rupees = int(round(rupees / 500) * 500) if rng.random() < P.BIG_ORDER_ROUND_500 else int(rupees)
        ptype = "P2P" if rng.random() < P.BIG_ORDER_P2P else "P2M"
        ctx.pay(pid, at(day, shop_seconds(rng, 1)[0]), rupees, ptype, "SALE", "big_one_off")


def _family_time(rng, day: date) -> datetime:
    if rng.random() < P.FAMILY_EVENING:
        return at(day, window_seconds(rng, 1, time(18, 0), P.SHOP_CLOSE)[0])
    return at(day, window_seconds(rng, 1, time(8, 0), time(18, 0))[0])


def non_round_rupees(rng) -> int:
    """A multiple of ₹50 that is not a multiple of ₹100, e.g. 750, 1250, 2350."""
    lo, hi = P.NON_ROUND_RANGE
    return int(rng.integers(lo // 100, hi // 100)) * 100 + 50


def _family(ctx: _Ctx, pid: str, amounts=P.FAMILY_AMOUNTS, gap=P.FAMILY_GAP_DAYS, p2p=P.FAMILY_P2P,
            non_round=P.FAMILY_NON_ROUND) -> None:
    ctx.specs.append(("family", pid, {"amounts": amounts, "gap": gap, "p2p": p2p, "non_round": non_round}))
    rng = ctx.rng
    scale = 1.0 / ctx.family_rate  # interval between transfers: x2 for rate x0.5, /4 for rate x4
    d = int(rng.integers(0, gap[1]))
    if ctx.family_rate != 1.0:
        d = int(d * scale)
    while d < len(DAYS):
        ptype = "P2P" if rng.random() < p2p else "P2M"
        rupees = non_round_rupees(rng) if rng.random() < non_round else int(rng.choice(amounts))
        ctx.pay(pid, _family_time(rng, DAYS[d]), rupees, ptype, "FAMILY", "family")
        step = int(rng.integers(gap[0], gap[1] + 1))
        d += step if ctx.family_rate == 1.0 else max(1, round(step * scale))


def _friend(ctx: _Ctx, pid: str) -> None:
    ctx.specs.append(("friend", pid, {}))
    rng = ctx.rng
    k = int(rng.integers(P.FRIEND_TIMES[0], P.FRIEND_TIMES[1] + 1))
    if ctx.family_rate != 1.0:
        k = min(len(DAYS), max(1, round(k * ctx.family_rate)))
    for d in sorted(rng.choice(len(DAYS), size=k, replace=False)):
        ts = at(DAYS[d], window_seconds(rng, 1, time(8, 0), P.SHOP_CLOSE)[0])
        rupees = non_round_rupees(rng) if rng.random() < P.FRIEND_NON_ROUND else int(rng.choice(P.FRIEND_AMOUNTS))
        ctx.pay(pid, ts, rupees, "P2P", "FAMILY", "friend_loan")


def _mixed(ctx: _Ctx, pid: str) -> None:
    rng, cat = ctx.rng, ctx.merchant["business_category"]
    d = int(rng.integers(0, P.MIXED_GAP_DAYS[1]))
    while d < len(DAYS):
        if rng.random() < P.MIXED_SALE_SHARE:
            rupees = int(customer_rupees(rng, cat, 1)[0])
            if rupees % 5 == 0:
                rupees += int(rng.integers(1, 5))  # SALE ones are non-round
            ctx.pay(pid, at(DAYS[d], shop_seconds(rng, 1)[0]), rupees, "P2M", "SALE", "mixed_relative")
        else:
            ctx.pay(pid, _family_time(rng, DAYS[d]), int(rng.choice(P.FAMILY_AMOUNTS)), "P2P", "FAMILY", "mixed_relative")
        d += int(rng.integers(P.MIXED_GAP_DAYS[0], P.MIXED_GAP_DAYS[1] + 1))


def _credit_settlement(ctx: _Ctx, pid: str) -> None:
    """A regular who settles a tab weekly or monthly by P2P, round amount, mostly in the evening (SALE)."""
    rng = ctx.rng
    gap = P.CREDIT_GAP_DAYS["weekly" if rng.random() < 0.5 else "monthly"]
    d = int(rng.integers(0, gap[1]))
    while d < len(DAYS):
        rupees = int(round(rng.uniform(*P.CREDIT_AMOUNT) / 100) * 100)
        if rng.random() < P.CREDIT_EVENING:
            ts = at(DAYS[d], window_seconds(rng, 1, time(18, 0), P.SHOP_CLOSE)[0])
        else:
            ts = at(DAYS[d], window_seconds(rng, 1, P.SHOP_OPEN, time(18, 0))[0])
        ctx.pay(pid, ts, rupees, "P2P", "SALE", "credit_settlement")
        d += int(rng.integers(gap[0], gap[1] + 1))


def _new_person(ctx: _Ctx, kind_label: str) -> str:
    return ctx.payer(ctx.ids.take(kind_label), person_name(ctx.rng), "PERSONAL")


def _new_business(ctx: _Ctx) -> str:
    rng = ctx.rng
    kind = "BUSINESS" if rng.random() < P.BUSINESS_VPA else "PERSONAL"
    return ctx.payer(ctx.ids.take("business"), str(rng.choice(BUSINESS_NAMES)), kind)


# --- per merchant ---------------------------------------------------------------
def _merchant_payments(ctx: _Ctx, scale: float) -> list[str]:
    rng, mid = ctx.rng, ctx.merchant["merchant_id"]
    pool = _regular_pool(ctx)
    _customers(ctx, scale, pool)
    _big_orders(ctx)

    if mid == "M001":
        _business_buyer(ctx, ctx.payer("P20001", *NAMED_PAYERS["P20001"]), amount=(600, 1500), p2m=1.0)
        _family(ctx, ctx.payer("P90002", *NAMED_PAYERS["P90002"]), amounts=[1000, 1500, 2000, 3000], gap=(5, 9), p2p=1.0,
                non_round=0.0)  # Karthik as in DATA 3.2
        ctx.payer("P90003", *NAMED_PAYERS["P90003"])
        for day, t, paise, ptype, label in SELVI_SCHEDULE:
            ctx.pay("P90003", datetime.combine(day, t, tzinfo=IST), paise, ptype, label, "mixed_relative", paise=True)
        for pid, day, rupees in FIXED_UNANSWERED:
            ctx.payer(pid, *NAMED_PAYERS[pid])
            ctx.pay(pid, datetime.combine(day, FIXED_UNANSWERED_TIME, tzinfo=IST), rupees, "P2P", "FAMILY",
                    "fixed_unanswered", protected=True)
        n_business, n_family, has_mixed = 0, 0, False  # named payers fill these roles
    else:
        n_business = int(rng.integers(P.BUSINESS_COUNT[0], P.BUSINESS_COUNT[1] + 1))
        n_family = int(rng.integers(P.FAMILY_COUNT[0], P.FAMILY_COUNT[1] + 1))
        has_mixed = rng.random() < P.MIXED_MERCHANT_SHARE
        if mid == "M002":
            _business_buyer(ctx, ctx.payer("P20011", *NAMED_PAYERS["P20011"]))
            n_business = max(0, n_business - 1)

    for _ in range(n_business):
        _business_buyer(ctx, _new_business(ctx))
    for _ in range(n_family):
        _family(ctx, _new_person(ctx, "family"))
    for _ in range(int(rng.integers(P.FRIEND_COUNT[0], P.FRIEND_COUNT[1] + 1))):
        _friend(ctx, _new_person(ctx, "family"))
    if has_mixed:
        _mixed(ctx, _new_person(ctx, "family"))
    for _ in range(int(rng.integers(P.CREDIT_COUNT[0], P.CREDIT_COUNT[1] + 1))):
        _credit_settlement(ctx, _new_person(ctx, "customer"))
    return pool


def _rescale_family(ctx: _Ctx, rows: list[dict], refunds: list[dict], reversals: list[dict], seed: int,
                    family_rate: float) -> tuple[list[dict], list[dict], list[dict]]:
    """Robustness only. The merchant was generated exactly as at rate 1 (same payers, customers, refunds).
    Replace only the family/friend payments: the same payers' transfers are regenerated at the scaled rate from a
    separate random stream, transaction IDs are renumbered in time order, customer refunds are mapped across, and
    reversals of the old family/friend payments are dropped (the new ones get none)."""
    mid = ctx.merchant["merchant_id"]
    ctx2 = _Ctx(merchant=ctx.merchant, rng=np.random.default_rng([seed, int(mid[1:]), 77]), ids=ctx.ids,
                payers=ctx.payers, rows=[], family_rate=family_rate)
    for kind, pid, kw in list(ctx.specs):
        if kind == "family":
            _family(ctx2, pid, **kw)
        else:
            _friend(ctx2, pid)
    keep = [r for r in rows if r["payer_role"] not in ("family", "friend_loan")]
    old_ids = [r["transaction_id"] for r in keep]
    new_rows = _assign_ids(keep + ctx2.rows)
    mapping = dict(zip(old_ids, (r["transaction_id"] for r in keep)))
    refunds = [dict(x, transaction_id=mapping[x["transaction_id"]]) for x in refunds]  # refunds are on sales only
    reversals = [dict(x, transaction_id=mapping[x["transaction_id"]]) for x in reversals if x["transaction_id"] in mapping]
    return new_rows, refunds, reversals


def _assign_ids(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda r: r["ts"])  # stable: equal timestamps keep generation order
    per_day: Counter = Counter()
    for r in rows:
        day = r["ts"].strftime("%Y%m%d")
        per_day[day] += 1
        if per_day[day] > 999:
            raise RuntimeError("more than 999 payments in a day")
        r["transaction_id"] = f"TXN-{r['merchant_id']}-{day}-{per_day[day]:03d}"
    return rows


def _refunds_reversals(rows: list[dict], rng) -> tuple[list[dict], list[dict]]:
    refunds, reversals = [], []
    n_refund = 0
    for r in rows:
        if r["protected"]:
            continue
        if r["true_label"] == "SALE" and rng.random() < P.REFUND_RATE:
            ts = r["ts"] + timedelta(seconds=int(rng.integers(300, P.REFUND_MAX_DAYS * 86400)))
            if ts > PERIOD_END:
                continue
            if rng.random() < P.REFUND_FULL_SHARE:
                amount = r["amount_paise"]
            else:
                amount = int(round(r["amount_paise"] * rng.uniform(*P.REFUND_PARTIAL) / 100)) * 100
                amount = min(max(amount, 100), r["amount_paise"])
            n_refund += 1
            refunds.append({
                "refund_id": f"RF-{r['merchant_id']}-{n_refund:06d}", "transaction_id": r["transaction_id"],
                "amount_paise": amount, "ts": ts, "reason": str(rng.choice(CUSTOMER_REASONS_REFUND)),
            })
            continue  # a payment is refunded or reversed, never both
        if rng.random() < P.REVERSAL_RATE:
            ts = r["ts"] + timedelta(seconds=int(rng.integers(60, P.REVERSAL_MAX_DAYS * 86400)))
            if ts <= PERIOD_END:
                reversals.append({"transaction_id": r["transaction_id"], "ts": ts, "reason": "Bank reversal"})
    refunds.sort(key=lambda x: x["ts"])
    return refunds, reversals


def _expenses(merchant: dict, rng) -> list[dict]:
    mid, cat, lang = merchant["merchant_id"], merchant["business_category"], merchant["preferred_language"]
    transport_weekday = int(rng.integers(0, 7))
    out = []

    def add(day, category, lo, hi, start, end):
        rupees = int(round(rng.uniform(lo, hi) / 10) * 10)
        voice = rng.random() < P.EXPENSE_VOICE_SHARE
        out.append({
            "client_request_id": make_uuid(rng), "merchant_id": mid, "amount_paise": rupees * 100,
            "category": category, "description": EXPENSE_TEXT[mid][category],
            "ts": at(day, window_seconds(rng, 1, start, end)[0]),
            "input_source": "VOICE" if voice else "MANUAL", "language": lang if voice else None,
            "utterance_text": None, "voice_log_id": None,
        })

    for day in DAYS:
        if cat in ("VEGETABLES", "FRUITS") or (cat == "MIXED_KIRANA" and day.weekday() in (0, 3)):
            add(day, "STOCK_PURCHASE", *STOCK_RANGE[cat], time(5, 0), time(6, 30))
        if day.weekday() == transport_weekday:
            add(day, "TRANSPORT", 300, 800, time(7, 0), time(10, 0))
        if day.day in (1, 16):
            add(day, "PACKAGING", 200, 500, time(11, 0), time(15, 0))
        if day.day == 5:
            add(day, "RENT", 6000, 6000, time(10, 0), time(12, 0))
    return out


# --- top level --------------------------------------------------------------------
def merchant_list(seed: int) -> list[dict]:
    rng = np.random.default_rng([seed, 0])
    cats = []
    for counts in (P.TRAIN_CATEGORY_COUNTS, P.TEST_CATEGORY_COUNTS):  # proportions kept within each group
        group = [c for c, n in counts.items() for _ in range(n)]
        rng.shuffle(group)
        cats += group
    out = [dict(m, city="Chennai", created_at=P.MERCHANT_CREATED_AT, volume_scale=1.0) for m in DEMO_MERCHANTS]
    for mid, cat in zip(P.EVAL_MERCHANTS, cats):
        mrng = np.random.default_rng([seed, int(mid[1:]), 1])
        out.append({
            "merchant_id": mid, "display_name": f"Synthetic {cat.replace('_', ' ').title()} {mid[1:]}",
            "owner_name": f"Owner {mid[1:]}", "business_category": cat, "preferred_language": "ta",
            "city": "Chennai", "created_at": P.MERCHANT_CREATED_AT,
            "volume_scale": round(float(mrng.uniform(*P.SCALE_RANGE)), 4),
        })
    return out


def generate(seed: int = 42, only: list[str] | None = None, family_rate: float = 1.0) -> Generated:
    """family_rate != 1.0 is for robustness experiments only (family and friend transfer rates; number of
    family/friend payers and all customer behaviour unchanged)."""
    merchants = [m for m in merchant_list(seed) if only is None or m["merchant_id"] in only]
    payers: dict[str, tuple[str, str]] = {pid: v for pid, v in NAMED_PAYERS.items()}
    demo_ids = DemoIds()
    payments, refunds, reversals, expenses, pools = [], [], [], [], {}

    for m in merchants:
        mid = m["merchant_id"]
        rng = np.random.default_rng([seed, int(mid[1:])])
        ids = demo_ids if mid in ("M001", "M002", "M003") else EvalIds(mid)
        ctx = _Ctx(merchant=m, rng=rng, ids=ids, payers=payers, rows=[])  # always the rate-1 stream
        pools[mid] = _merchant_payments(ctx, m["volume_scale"])
        rows = _assign_ids(ctx.rows)
        rf, rv = _refunds_reversals(rows, rng)
        if family_rate != 1.0:
            rows, rf, rv = _rescale_family(ctx, rows, rf, rv, seed, family_rate)
        payments += rows
        refunds += rf
        reversals += rv
        if mid in EXPENSE_TEXT:
            expenses += _expenses(m, rng)

    iso = lambda dt: dt.isoformat(timespec="seconds")  # noqa: E731
    pay_df = pd.DataFrame(payments)
    pay_df["timestamp"] = pay_df["ts"].map(iso)
    labels = pay_df[["transaction_id", "true_label", "payer_role"]].copy()
    pay_cols = ["transaction_id", "merchant_id", "payer_id", "payer_name", "payer_vpa_kind", "amount_paise",
                "payment_type", "timestamp", "description"]
    ref_df = pd.DataFrame(refunds, columns=["refund_id", "transaction_id", "amount_paise", "ts", "reason"])
    ref_df["timestamp"] = ref_df["ts"].map(iso)
    rev_df = pd.DataFrame(reversals, columns=["transaction_id", "ts", "reason"])
    rev_df["timestamp"] = rev_df["ts"].map(iso)
    exp_df = pd.DataFrame(expenses)
    exp_df["timestamp"] = exp_df["ts"].map(iso) if len(exp_df) else []
    exp_cols = ["client_request_id", "merchant_id", "amount_paise", "category", "description", "timestamp",
                "input_source", "language", "utterance_text", "voice_log_id"]
    fam = pd.DataFrame([f for f in FAMILY_CONFIG if only is None or f["merchant_id"] in only],
                       columns=["merchant_id", "payer_id", "relation_label", "added_at", "added_via"])
    return Generated(
        merchants=pd.DataFrame(merchants),
        payers=pd.DataFrame([{"payer_id": k, "payer_name": v[0], "payer_vpa_kind": v[1]} for k, v in sorted(payers.items())]),
        payments=pay_df[pay_cols].reset_index(drop=True),
        refunds=ref_df[["refund_id", "transaction_id", "amount_paise", "timestamp", "reason"]],
        reversals=rev_df[["transaction_id", "timestamp", "reason"]],
        expenses=exp_df[exp_cols] if len(exp_df) else pd.DataFrame(columns=exp_cols),
        labels=labels.reset_index(drop=True),
        family_config=fam,
        regular_pools=pools,
    )
