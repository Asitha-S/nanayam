"""python -m ml.evaluate   (after python -m ml.train)

Evaluation protocol DATA_AND_LOGIC 11: test merchants M171-M280 (never seen in training), test period
2026-10-16..2026-11-14 (after the training period). Every condition runs the same model, the same
threshold and the same simulated-answer random stream:

  A  always SALE                       C  model, no feedback (answers not stored)
  B  naive rule: P2P + round ₹100      D  model + payer memory
                                       E  full system: payer memory + "remember" (p = 0.5 after a FAMILY answer)

Test merchants start every condition with empty memory and no configured family on 2026-10-16.
Simulated merchant answers are the true label, flipped with probability 0.02. Reversals are ignored here.
Writes data/eval/runs/{run_id}.json and data/eval/latest.json (the GET /evaluation response). Never edit by hand.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date, datetime

import joblib
import numpy as np
import pandas as pd

from .common import ARTIFACTS, GENERATED, REPO_ROOT
from .simulate import replay, simulated_answers
from .train import ece
from app.classifier import procedure  # noqa: E402
from app.classifier.features import FEATURES  # noqa: E402

SEED = 42
ANSWER_ERROR_RATE = 0.02
TEST_MERCHANTS = [f"M{n}" for n in range(171, 281)]
TEST_PERIOD = (date(2026, 10, 16), date(2026, 11, 14))
WEEKS = [("Days 1–7", 0, 6), ("Days 8–14", 7, 13), ("Days 15–21", 14, 20), ("Days 22–30", 21, 29)]
CONDITIONS = ("A", "B", "C", "D", "E")
CONDITION_NAMES = {"A": "Always SALE", "B": "Naive rule (P2P + round ₹100 = FAMILY)", "C": "Model, no feedback",
                   "D": "Model + payer memory", "E": "Full system (payer memory + remember)"}
OUT_DIR = REPO_ROOT / "data" / "eval"


def _counted(count: int, of: int) -> dict:
    return {"count": int(count), "of": int(of), "rate": round(count / of, 4) if of else None}


def metrics(d: pd.DataFrame, t: pd.DataFrame, cond: str) -> dict:
    truth = t.true_label.to_numpy()
    auto = (d.action == "AUTO_CLASSIFY").to_numpy()
    ask = ~auto
    sug, final, src = d.suggested.to_numpy(), d.final.to_numpy(), d.source.to_numpy()
    n_merchants, n_days = t.merchant_id.nunique(), (TEST_PERIOD[1] - TEST_PERIOD[0]).days + 1
    day_idx = (pd.to_datetime(t.date) - pd.Timestamp(TEST_PERIOD[0])).dt.days.to_numpy()
    is_fam, is_sale = truth == "FAMILY", truth == "SALE"
    by_source = {}
    for s in ("MODEL", "PAYER_MEMORY", "MERCHANT_CONFIG"):
        m = auto & (src == s)
        if cond in ("C", "D", "E"):
            by_source[s] = {"correct": int((sug[m] == truth[m]).sum()), "of": int(m.sum()),
                            "precision": round(float((sug[m] == truth[m]).mean()), 4) if m.any() else None}
    weeks = []
    for _, lo, hi in WEEKS:
        w = (day_idx >= lo) & (day_idx <= hi)
        weeks.append(round(float(ask[w].sum()) / (n_merchants * (hi - lo + 1)), 2))
    cfg = auto & (src == "MERCHANT_CONFIG")
    return {
        "name": CONDITION_NAMES[cond],
        "precision_auto": round(float((sug[auto] == truth[auto]).mean()), 4) if auto.any() else None,
        "precision_auto_by_source": by_source,
        "coverage": round(float(auto.mean()), 4),
        "auto_decisions": int(auto.sum()),
        "questions": int(ask.sum()),
        "questions_per_merchant_per_day": round(float(ask.sum()) / (n_merchants * n_days), 2),
        "overall_accuracy": round(float((final == truth).mean()), 4),
        "family_recall_final": _counted(((final == "FAMILY") & is_fam).sum(), is_fam.sum()),
        "income_wrongly_removed": {**_counted(((final == "FAMILY") & is_sale).sum(), is_sale.sum()),
                                   "silent": int((auto & is_sale & (sug == "FAMILY")).sum()),
                                   "merchant_answer_errors": int((ask & is_sale & (final == "FAMILY")).sum())},
        "silent_family_errors": _counted((auto & is_sale & (sug == "FAMILY")).sum(), is_sale.sum()),
        "silent_sale_errors": _counted((auto & is_fam & (sug == "SALE")).sum(), is_fam.sum()),
        "config_errors": _counted((cfg & (sug != truth)).sum(), cfg.sum()),
        "questions_per_day_by_week": weeks,
        "confusion_matrix_auto": {"labels": ["SALE", "FAMILY"], "rows": "true label", "columns": "decision",
                                  "matrix": [[int((auto & is_sale & (sug == "SALE")).sum()), int((auto & is_sale & (sug == "FAMILY")).sum())],
                                             [int((auto & is_fam & (sug == "SALE")).sum()), int((auto & is_fam & (sug == "FAMILY")).sum())]]},
    }


def curve_c(t: pd.DataFrame, q: np.ndarray) -> list[dict]:
    """Condition C precision_auto and coverage for tau 0.50-0.99 (vectorised; same rules as procedure.run)."""
    truth = t.true_label.to_numpy()
    new, amount = t.is_new_payer.to_numpy() > 0, t.amount_paise.to_numpy()
    suggested = np.where(q >= 0.5, "FAMILY", "SALE")
    conf = np.maximum(q, 1 - q)
    forced = (new & (amount >= procedure.FIRST_TIME_LARGE_PAISE)) | (suggested == "FAMILY")  # 5b, 5c (5a needs memory)
    out = []
    for tau in [round(0.50 + i / 100, 2) for i in range(50)]:
        auto = (conf >= tau) & ~forced
        out.append({"threshold": tau, "coverage": round(float(auto.mean()), 4),
                    "precision_auto": round(float((suggested[auto] == truth[auto]).mean()), 4) if auto.any() else None})
    return out


def main() -> None:
    current = json.loads((ARTIFACTS / "current.json").read_text(encoding="utf-8"))
    art = joblib.load(REPO_ROOT / current["artifact"])
    tau = float(current["threshold"])
    k = float(current.get("k", 2.0))
    feats = pd.read_parquet(GENERATED / "features.parquet")
    t = feats[feats.merchant_id.isin(TEST_MERCHANTS)
              & feats.date.between(TEST_PERIOD[0].isoformat(), TEST_PERIOD[1].isoformat())]
    t = t.sort_values(["merchant_id", "timestamp", "transaction_id"]).reset_index(drop=True)
    raw = art["model"].predict_proba(t[list(FEATURES)].to_numpy(float))[:, 1]
    q = art["calibrator"].predict(raw)

    truth = t.true_label.to_numpy()
    answers, remember = simulated_answers(truth, ANSWER_ERROR_RATE, np.random.default_rng([SEED, 2026]))

    conditions = {}
    for cond in CONDITIONS:
        conditions[cond] = metrics(replay(cond, t, q, tau, answers, remember, k=k), t, cond)
        c = conditions[cond]
        print(f"{cond} {c['name']:40s} precision_auto {c['precision_auto']}  coverage {c['coverage']}  "
              f"q/merchant/day {c['questions_per_merchant_per_day']}")

    curve = curve_c(t, q)
    at_tau = next(c for c in curve if c["threshold"] == round(tau, 2))
    assert at_tau["coverage"] == conditions["C"]["coverage"], "vectorised curve disagrees with the replay"
    ece_test, bins = ece(q, (truth == "FAMILY").astype(int))
    label_mix = json.loads((GENERATED / "label_mix.json").read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    now = datetime.now().astimezone()
    headline = lambda c: {  # noqa: E731
        "family_money_found": conditions[c]["family_recall_final"],
        "income_wrongly_removed": conditions[c]["income_wrongly_removed"],
        "questions_per_merchant_per_day": conditions[c]["questions_per_merchant_per_day"],
    }
    selection = art["threshold_selection"]
    pick = lambda c: {k: conditions[c][k] for k in ("precision_auto", "coverage", "questions_per_merchant_per_day",  # noqa: E731
                                                    "overall_accuracy")}
    result = {
        "run_id": f"eval-{now.strftime('%Y-%m-%d-%H%M%S')}",
        "created_at": now.isoformat(timespec="seconds"),
        "data_label": f"Synthetic data (generator seed {label_mix['seed']})",
        "model_version": current["model_version"],
        "threshold": tau,
        "split": {"train_merchants": 70, "test_merchants": len(TEST_MERCHANTS),
                  "test_period": f"{TEST_PERIOD[0]} to {TEST_PERIOD[1]}", "test_transactions": len(t)},
        "headline": {
            "note": "Show these first. precision_auto and precision by source are secondary and always shown next "
                    "to the always-SALE baseline (condition A).",
            "always_sale": headline("A"), "baseline": headline("C"), "with_feedback": headline("E"),
        },
        "threshold_selection": {k: selection[k] for k in ("set", "objective", "constraints", "tie_break",
                                                          "met_constraints", "chosen", "table")},
        "threshold_curve_calibration": [
            {"threshold": r["threshold"], "family_recall": r["family_recall"],
             "questions_per_merchant_per_day": r["questions_per_merchant_per_day"],
             "silent_errors": r["silent_errors"]["total"]}
            for r in selection["table"]],
        "baseline": pick("C"),
        "with_feedback": pick("E"),
        "questions_per_day_by_week": {"labels": [w[0] for w in WEEKS], "baseline": conditions["C"]["questions_per_day_by_week"],
                                      "with_feedback": conditions["E"]["questions_per_day_by_week"]},
        "pr_coverage_curve": curve,
        "confusion_matrix_auto": conditions["E"]["confusion_matrix_auto"],
        "calibration": {"ece": ece_test, "bins": bins},
        "merchant_answer_error_rate": ANSWER_ERROR_RATE,
        "label_mix": {"count_share": label_mix["count_share"], "value_share": label_mix["value_share"]},
        "conditions": conditions,
        "notes": {
            "family_metric_denominators": "family_recall_final: of all true FAMILY payments; silent_family_errors: of all "
                                          "true SALE payments; silent_sale_errors: of all true FAMILY payments; "
                                          "config_errors: of all MERCHANT_CONFIG decisions; income_wrongly_removed: "
                                          "true SALE payments whose final label is FAMILY (silent + merchant answer "
                                          "errors), of all true SALE payments.",
            "confusion_matrix_auto": "Top-level matrix is condition E (the full system); each condition has its own.",
            "reversals": "Ignored in the evaluation replay (0.1% of payments).",
        },
        "seed": SEED,
        "git_commit": commit or None,
    }
    runs = OUT_DIR / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (runs / f"{result['run_id']}.json").write_text(text, encoding="utf-8")
    (OUT_DIR / "latest.json").write_text(text, encoding="utf-8")
    print(f"-> {OUT_DIR / 'latest.json'}  (test transactions {len(t):,}, FAMILY {int((truth == 'FAMILY').sum())})")


if __name__ == "__main__":
    main()
