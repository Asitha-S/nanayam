"""scripts/robustness.py guards and generator family-rate scaling (no full populations built here)."""
import pytest

from data.generator.generate import generate
from scripts import robustness


def test_robustness_refuses_the_final_holdout_seed():
    with pytest.raises(SystemExit):
        robustness.population(42)


def test_family_rate_scales_family_and_friends_only():
    base = generate(7, only=["M171"]).payments.merge(generate(7, only=["M171"]).labels, on="transaction_id")
    more = generate(7, only=["M171"], family_rate=4.0)
    more = more.payments.merge(more.labels, on="transaction_id")
    fam = lambda df: df[df.payer_role.isin(["family", "friend_loan"])]  # noqa: E731
    assert len(fam(more)) > 2.5 * len(fam(base))
    assert fam(more).payer_id.nunique() == fam(base).payer_id.nunique()  # same number of family/friend payers
    others = lambda df: df[~df.payer_role.isin(["family", "friend_loan"])]  # noqa: E731
    cols = ["payer_id", "amount_paise", "payment_type", "timestamp", "payer_role"]
    assert others(more)[cols].reset_index(drop=True).equals(others(base)[cols].reset_index(drop=True))  # customers identical
    fewer = generate(7, only=["M171"], family_rate=0.5)
    fewer = fewer.payments.merge(fewer.labels, on="transaction_id")
    assert len(fam(fewer)) < 0.75 * len(fam(base)) and fam(fewer).payer_id.nunique() == fam(base).payer_id.nunique()


def test_family_rate_keeps_customer_refunds():
    base, more = generate(7, only=["M171", "M172", "M173"]), generate(7, only=["M171", "M172", "M173"], family_rate=4.0)
    key = lambda g: sorted(g.refunds.merge(g.payments, on="transaction_id")[["payer_id", "timestamp_y", "amount_paise_x"]]  # noqa: E731
                           .itertuples(index=False))
    assert key(base) == key(more)


def test_family_rate_one_is_the_default_stream():
    a = generate(7, only=["M171"]).payments
    b = generate(7, only=["M171"], family_rate=1.0).payments
    assert a.equals(b)


def test_summary_is_within_one_experiment():
    def run(found, of, q):
        c = {"family_money_found": {"count": found, "of": of, "rate": found / of},
             "income_wrongly_removed": {"count": 1}, "silent_family_errors": {"count": 0},
             "silent_sale_errors": {"count": of - found}, "config_errors": {"count": 0},
             "questions_per_merchant_per_day": q, "precision_auto": 0.999, "coverage": 0.99}
        return {"conditions": {"E": c}}
    s = robustness.experiment_summary([run(90, 100, 0.4), run(80, 100, 0.6)])
    assert s["E"]["family_money_found_rate"] == {"mean": 0.85, "min": 0.8, "max": 0.9}
    assert s["E"]["questions_per_merchant_per_day"] == {"mean": 0.5, "min": 0.4, "max": 0.6}
