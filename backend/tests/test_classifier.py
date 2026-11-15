"""Decision procedure (DATA 5.6), payer memory (6), reasons (5.5) and features (5.1, 11.2)."""
import random
import sqlite3
from datetime import datetime, timedelta

import pytest

from app import clock
from app.classifier import procedure
from app.classifier.features import (FEATURES, MIN_WINDOW_PAYMENTS, MerchantHistory, Pay, PayerStats, build,
                                     history_from_db, vector)
from app.config import DEMO_DATA_DIR

IST = clock.IST
pytestmark = pytest.mark.timeout(900)  # builds generator data / walks the seed


# --- payer memory worked examples (DATA 6), tau 0.90 -------------------------------------
@pytest.mark.parametrize("q, nf, ns, p, action", [
    (0.71, 0, 0, 0.71, "ASK_MERCHANT"),      # and rule 5c
    (0.71, 1, 0, 0.807, "ASK_MERCHANT"),
    (0.71, 2, 0, 0.855, "ASK_MERCHANT"),
    (0.71, 4, 0, 0.903, "AUTO_CLASSIFY"),    # AUTO FAMILY
    (0.30, 3, 0, 0.72, "ASK_MERCHANT"),
    (0.10, 0, 3, 0.04, "AUTO_CLASSIFY"),     # AUTO SALE, confidence 0.96
    (0.60, 2, 2, 0.533, "ASK_MERCHANT"),     # mixed payer rule (spec table said 0.55: arithmetic slip)
])
def test_feedback_examples(q, nf, ns, p, action):
    o = procedure.run(q=q, n_family=nf, n_sale=ns, is_new_payer=False, amount_paise=200000, payment_type="P2P", tau=0.90)
    assert round(o.p_final, 3) == p and o.action == action
    assert o.source == ("RULE" if o.rules else "PAYER_MEMORY" if nf + ns else "MODEL")


def test_auto_sale_example_confidence():
    o = procedure.run(q=0.10, n_family=0, n_sale=3, is_new_payer=False, amount_paise=4000, payment_type="P2M", tau=0.9)
    assert (o.suggested, round(o.confidence, 2), o.classification) == ("SALE", 0.96, "SALE")


@pytest.mark.parametrize("q", [0.5, 0.71, 0.95, 0.999, 1.0])
def test_rule_5c_family_suggestion_without_confirmation_always_asks(q):
    o = procedure.run(q=q, n_family=0, n_sale=0, is_new_payer=False, amount_paise=200000, payment_type="P2P", tau=0.5)
    assert o.suggested == "FAMILY" and o.action == "ASK_MERCHANT" and "FAMILY_NEEDS_CONFIRMATION" in o.rules
    assert o.classification == "PENDING" and o.source == "RULE"


def test_rule_5b_first_time_large():
    o = procedure.run(q=0.0, n_family=0, n_sale=0, is_new_payer=True, amount_paise=500000, payment_type="P2M", tau=0.9)
    assert o.suggested == "SALE" and o.action == "ASK_MERCHANT" and o.rules == ("FIRST_TIME_LARGE",)
    small = procedure.run(q=0.0, n_family=0, n_sale=0, is_new_payer=True, amount_paise=499900, payment_type="P2M", tau=0.9)
    assert small.action == "AUTO_CLASSIFY"


def test_rule_5a_mixed_payer():
    o = procedure.run(q=0.0, n_family=1, n_sale=3, is_new_payer=False, amount_paise=30000, payment_type="P2M", tau=0.5)
    assert "MIXED_PAYER" in o.rules and o.action == "ASK_MERCHANT"
    two = procedure.run(q=0.0, n_family=1, n_sale=1, is_new_payer=False, amount_paise=30000, payment_type="P2M", tau=0.5)
    assert "MIXED_PAYER" not in two.rules  # needs at least 3 answers


def test_merchant_config_has_no_confidence_but_q_is_computed():
    o = procedure.run(q=0.3, n_family=0, n_sale=0, configured_family=True, is_new_payer=False, amount_paise=200000,
                      payment_type="P2P", tau=0.99)
    assert (o.suggested, o.action, o.source, o.confidence, o.confidence_kind, o.q_model) == (
        "FAMILY", "AUTO_CLASSIFY", "MERCHANT_CONFIG", None, "NONE", 0.3)
    assert procedure.reasons(o, None, 0, 0) == ["Marked as family by merchant"]
    c = procedure.run(q=0.3, n_family=0, n_sale=0, configured_customer=True, is_new_payer=False, amount_paise=200000,
                      payment_type="P2P", tau=0.99)
    assert (c.suggested, c.action, c.source, c.confidence) == ("SALE", "AUTO_CLASSIFY", "MERCHANT_CONFIG", None)
    assert procedure.reasons(c, None, 0, 0) == ["Marked as customer by merchant"]


def _cfg(*, family=False, customer=False, q, ptype, amount):
    return procedure.run(q=q, n_family=0, n_sale=0, is_new_payer=False, amount_paise=amount, payment_type=ptype,
                         tau=0.99, configured_family=family, configured_customer=customer)


@pytest.mark.parametrize("q, ptype, amount, asks", [
    (0.02, "P2M", 125_000, True),      # boundary: q <= 0.02 fires
    (0.0201, "P2M", 125_000, False),
    (0.0, "P2M", 120_000, False),      # round to Rs 100 -> no guardrail
    (0.0, "P2M", 120_050, True),       # Rs 1,200.50 is not round to Rs 100
    (0.0, "P2P", 125_000, False),      # P2P -> no guardrail
])
def test_family_guardrail_5d_boundaries(q, ptype, amount, asks):
    o = _cfg(family=True, q=q, ptype=ptype, amount=amount)
    if asks:
        assert (o.action, o.source, o.suggested, o.rules) == ("ASK_MERCHANT", "RULE", "SALE", ("FAMILY_GUARDRAIL",))
        assert o.confidence == max(q, 1 - q) and o.confidence_kind == "MODEL"
        assert procedure.reasons(o, None, 0, 0)[0] == "Looks like a shop sale from a family payer"
    else:
        assert (o.action, o.source, o.suggested) == ("AUTO_CLASSIFY", "MERCHANT_CONFIG", "FAMILY")


@pytest.mark.parametrize("q, ptype, amount, asks", [
    (0.98, "P2P", 200_000, True),      # boundary: q >= 0.98 fires
    (0.9799, "P2P", 200_000, False),
    (1.0, "P2P", 210_000, False),      # round to Rs 100 but not Rs 500 -> no guardrail
    (1.0, "P2P", 250_000, True),       # Rs 2,500 is round to Rs 500
    (1.0, "P2M", 200_000, False),      # P2M -> no guardrail
])
def test_customer_guardrail_1b_boundaries(q, ptype, amount, asks):
    o = _cfg(customer=True, q=q, ptype=ptype, amount=amount)
    if asks:
        assert (o.action, o.source, o.suggested, o.rules) == ("ASK_MERCHANT", "RULE", "FAMILY", ("CUSTOMER_GUARDRAIL",))
        assert procedure.reasons(o, None, 0, 0)[0] == "Looks like family money from a customer"
    else:
        assert (o.action, o.source, o.suggested) == ("AUTO_CLASSIFY", "MERCHANT_CONFIG", "SALE")


def test_memory_k_is_a_parameter():
    assert round(procedure.memory_p(0.71, 1, 0, k=1), 3) == 0.855 and round(procedure.memory_p(0.71, 1, 0, k=4), 3) == 0.768


def _pay(amount=200000, ptype="P2P", kind="PERSONAL", ts="2026-11-15T19:42:10+05:30", payer="P1", txn="T1"):
    return Pay(txn, payer, amount, ptype, kind, clock.parse(ts))


def test_reasons_priority_and_limit():
    f = build(_pay(), "VEGETABLES", [], PayerStats())
    o = procedure.run(q=0.9, n_family=0, n_sale=0, is_new_payer=True, amount_paise=200000, payment_type="P2P", tau=0.9)
    assert procedure.reasons(o, f, 0, 0) == [
        "Family money is only excluded after the merchant confirms", "New payer", "P2P transfer", "Round amount"]
    regular = build(_pay(amount=12000, ptype="P2M"), "VEGETABLES", [],
                    PayerStats(count=8, p2p=1, amount_sum=96000, round100=2, last_ts=clock.parse("2026-11-14T08:00:00+05:30")))
    o2 = procedure.run(q=0.01, n_family=0, n_sale=0, is_new_payer=False, amount_paise=12000, payment_type="P2M", tau=0.9)
    assert procedure.reasons(o2, regular, 0, 0) == ["Regular customer", "Typical sale amount"]


# --- features --------------------------------------------------------------------------------
def test_feature_values():
    f = build(_pay(), "VEGETABLES", [], PayerStats())
    assert len(vector(f)) == len(FEATURES)
    assert f["amt_ratio_median"] == 200000 / 12000  # default category median with < 50 payments
    assert (f["is_round_100"], f["is_round_500"], f["is_round_1000"], f["is_p2p"]) == (1.0, 1.0, 1.0, 1.0)
    assert (f["hour"], f["is_evening"], f["day_of_week"], f["is_sunday"]) == (19.0, 1.0, 6.0, 1.0)  # 15 Nov 2026 is a Sunday
    assert (f["is_new_payer"], f["payer_prior_count"], f["payer_amt_ratio"], f["days_since_payer_last"]) == (1.0, 0.0, 1.0, 999.0)
    assert f["cat_VEGETABLES"] == 1.0 and f["cat_FRUITS"] == 0.0
    window = sorted([10000] * MIN_WINDOW_PAYMENTS)
    assert build(_pay(), "VEGETABLES", window, PayerStats())["amt_ratio_median"] == 20.0


def test_history_window_and_order():
    h = MerchantHistory("VEGETABLES")
    t0 = datetime(2026, 10, 1, 8, 0, tzinfo=IST)
    for i in range(60):
        h.add(Pay(f"T{i:03d}", f"P{i}", 10000, "P2M", "PERSONAL", t0 + timedelta(hours=i)))
    late = Pay("T999", "P1", 20000, "P2M", "PERSONAL", t0 + timedelta(days=13, hours=12))
    assert h.features(late)["amt_ratio_median"] == 2.0
    gone = Pay("T998", "P1", 20000, "P2M", "PERSONAL", t0 + timedelta(days=20))  # all older than 14 days
    assert h.features(gone)["amt_ratio_median"] == 20000 / 12000


SEED = DEMO_DATA_DIR / "seed.db"


@pytest.mark.skipif(not SEED.exists(), reason="run python -m data.seed_demo first")
def test_db_path_matches_incremental_replay_and_ignores_future():
    """Same payment -> identical vector from the live DB path and the training replay. The DB holds the
    merchant's FUTURE payments too, so equality also shows that no later payment leaks in (DATA 11.2)."""
    conn = sqlite3.connect(f"file:{SEED.as_posix()}?mode=ro", uri=True)
    try:
        rng = random.Random(11)
        for mid in ("M001", "M002", "M003"):
            category = conn.execute("SELECT business_category FROM merchants WHERE merchant_id = ?", (mid,)).fetchone()[0]
            rows = conn.execute(
                "SELECT p.transaction_id, p.payer_id, p.amount_paise, p.payment_type, py.payer_vpa_kind, p.timestamp"
                " FROM payments p JOIN payers py USING (payer_id) WHERE merchant_id = ? ORDER BY timestamp, transaction_id",
                (mid,)).fetchall()
            sample = set(rng.sample(range(len(rows)), 70))
            h = MerchantHistory(category)
            for i, r in enumerate(rows):
                pay = Pay(r[0], r[1], r[2], r[3], r[4], clock.parse(r[5]))
                incremental = h.features(pay)
                if i in sample:
                    window, stats = history_from_db(conn, mid, pay)
                    assert build(pay, category, window, stats) == incremental, r[0]
                h.add(pay)
    finally:
        conn.close()
