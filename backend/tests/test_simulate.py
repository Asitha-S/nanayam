"""Evaluation replay (ml/simulate.py) and the holdout guard (ml/evaluate.py)."""
import sys

import numpy as np
import pandas as pd
import pytest

from ml import evaluate, experiment_log
from ml.simulate import replay, simulated_answers


def _frame(rows):
    """rows: (payer, amount_paise, payment_type, true_label); one merchant, in time order."""
    out = []
    for i, (payer, amount, ptype, label) in enumerate(rows):
        out.append({"merchant_id": "M999", "payer_id": payer, "transaction_id": f"T{i:03d}",
                    "timestamp": f"2026-10-16T{8 + i // 60:02d}:{i % 60:02d}:00+05:30", "date": "2026-10-16",
                    "amount_paise": amount, "is_new_payer": float(i == 0), "is_p2p": float(ptype == "P2P"),
                    "is_round_100": float(amount % 10_000 == 0), "true_label": label})
    return pd.DataFrame(out)


def test_e_remembers_family_then_auto_by_instruction():
    t = _frame([("P1", 200000, "P2P", "FAMILY"), ("P1", 200000, "P2P", "FAMILY")])
    q = np.array([0.9, 0.9])
    answers, remember = np.array(["FAMILY", "FAMILY"]), np.array([True, True])
    d = replay("E", t, q, 0.99, answers, remember, k=2)
    assert list(d.action) == ["ASK_MERCHANT", "AUTO_CLASSIFY"] and d.source[1] == "MERCHANT_CONFIG"
    assert d.rule[1] == "CONFIGURED_FAMILY"
    d_no = replay("D", t, q, 0.99, answers, remember, k=2)
    assert d_no.source[1] != "MERCHANT_CONFIG"  # D never remembers


def test_e_remembers_customer_only_after_sale_on_p2p():
    t = _frame([("P1", 200000, "P2P", "SALE"), ("P1", 200000, "P2P", "SALE"),
                ("P2", 12345, "P2M", "SALE"), ("P2", 12345, "P2M", "SALE")])
    q = np.array([0.6, 0.6, 0.6, 0.6])  # always asked unless configured
    answers, remember = np.array(["SALE"] * 4), np.array([True] * 4)
    d = replay("E", t, q, 0.99, answers, remember, k=2)
    assert d.rule[1] == "CONFIGURED_CUSTOMER" and d.action[1] == "AUTO_CLASSIFY" and d.suggested[1] == "SALE"
    assert d.source[3] != "MERCHANT_CONFIG"  # P2M: "Remember as customer" was never offered


def test_e_one_list_per_payer_and_guardrails_apply():
    t = _frame([("P1", 200000, "P2P", "SALE"),     # SALE + remember -> customer list
                ("P1", 200000, "P2P", "FAMILY"),   # customer guardrail (q 0.99) -> asked, FAMILY + remember -> family
                ("P1", 125050, "P2M", "SALE")])    # family guardrail 5d (q 0.0) -> asked
    q = np.array([0.6, 0.99, 0.0])
    answers, remember = np.array(["SALE", "FAMILY", "SALE"]), np.array([True, True, False])
    d = replay("E", t, q, 0.99, answers, remember, k=2)
    assert list(d.rule) == ["FAMILY_NEEDS_CONFIRMATION", "CUSTOMER_GUARDRAIL", "FAMILY_GUARDRAIL"]
    assert list(d.action) == ["ASK_MERCHANT"] * 3


def test_simulated_answers_error_rate_and_determinism():
    truth = np.array(["SALE"] * 9000 + ["FAMILY"] * 1000)
    a1, r1 = simulated_answers(truth, 0.10, np.random.default_rng([42, 2026]))
    a2, r2 = simulated_answers(truth, 0.10, np.random.default_rng([42, 2026]))
    assert (a1 == a2).all() and (r1 == r2).all()
    assert 0.08 < (a1 != truth).mean() < 0.12 and 0.45 < r1.mean() < 0.55


def test_holdout_needs_explicit_flag(monkeypatch):
    before = experiment_log.n_test_evaluations()
    lines = len(experiment_log.read())
    monkeypatch.setattr(sys, "argv", ["ml.evaluate"])
    with pytest.raises(SystemExit):
        evaluate.main()
    assert experiment_log.n_test_evaluations() == before and len(experiment_log.read()) == lines
