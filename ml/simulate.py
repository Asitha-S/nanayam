"""Replay of the decision procedure over a set of payments with a simulated merchant (DATA_AND_LOGIC 11.3).
Shared by k selection (ml.train, calibration set only) and the evaluation (ml.evaluate, robustness), so every
number comes from the same code as the live API's procedure.run.

  A  always SALE                       C  model, no feedback (answers not stored)
  B  naive rule: P2P + round ₹100      D  model + payer memory
                                       E  full system: payer memory + "remember" with probability 0.5
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .common import REPO_ROOT  # noqa: F401  (puts backend/ on sys.path)
from app.classifier import procedure  # noqa: E402

REMEMBER_PROBABILITY = 0.5


def simulated_answers(truth: np.ndarray, error_rate: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """(answers, remember coin) drawn once per payment, so every condition sees the same merchant."""
    flip = rng.random(len(truth)) < error_rate
    answers = np.where(flip, np.where(truth == "FAMILY", "SALE", "FAMILY"), truth)
    remember = rng.random(len(truth)) < REMEMBER_PROBABILITY
    return answers, remember


def replay(cond: str, t: pd.DataFrame, q: np.ndarray, tau: float, answers: np.ndarray, remember: np.ndarray,
           k: float = procedure.K) -> pd.DataFrame:
    """t must be sorted by (merchant_id, timestamp, transaction_id). Memory and configuration start empty."""
    n = len(t)
    merchant, payer = t.merchant_id.to_numpy(), t.payer_id.to_numpy()
    new, amount = t.is_new_payer.to_numpy() > 0, t.amount_paise.to_numpy()
    p2p, round100 = t.is_p2p.to_numpy() > 0, t.is_round_100.to_numpy() > 0
    action = np.empty(n, dtype=object)
    suggested = np.empty(n, dtype=object)
    source = np.empty(n, dtype=object)
    final = np.empty(n, dtype=object)
    memory: dict = defaultdict(lambda: [0, 0])
    family_cfg: set = set()
    for i in range(n):
        if cond == "A":
            a, s, src = "AUTO_CLASSIFY", "SALE", "BASELINE"
        elif cond == "B":
            a, s, src = "AUTO_CLASSIFY", ("FAMILY" if p2p[i] and round100[i] else "SALE"), "BASELINE"
        else:
            key = (merchant[i], payer[i])
            nf, ns = memory[key] if cond in ("D", "E") else (0, 0)
            o = procedure.run(q=float(q[i]), n_family=nf, n_sale=ns, is_new_payer=bool(new[i]),
                              amount_paise=int(amount[i]), payment_type="P2P" if p2p[i] else "P2M", tau=tau, k=k,
                              configured_family=cond == "E" and key in family_cfg)
            a, s, src = o.action, o.suggested, o.source
        action[i], suggested[i], source[i] = a, s, src
        if a == "AUTO_CLASSIFY":
            final[i] = s
        else:
            final[i] = answers[i]
            if cond in ("D", "E"):
                key = (merchant[i], payer[i])
                memory[key][0 if answers[i] == "FAMILY" else 1] += 1
                if cond == "E" and answers[i] == "FAMILY" and remember[i]:
                    family_cfg.add(key)
    return pd.DataFrame({"action": action, "suggested": suggested, "source": source, "final": final})


def silent_errors(d: pd.DataFrame, truth: np.ndarray) -> dict:
    auto = (d.action == "AUTO_CLASSIFY").to_numpy()
    sug = d.suggested.to_numpy()
    fam_as_sale = int((auto & (truth == "FAMILY") & (sug == "SALE")).sum())
    sale_as_fam = int((auto & (truth == "SALE") & (sug == "FAMILY")).sum())
    return {"family_counted_as_sale": fam_as_sale, "sale_removed_as_family": sale_as_fam, "total": fam_as_sale + sale_as_fam}
