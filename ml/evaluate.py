"""Evaluation (DATA_AND_LOGIC 11). Library functions used by the final holdout and by scripts/robustness.py.

FINAL HOLDOUT: python -m ml.evaluate --holdout
  test merchants M171-M280 of generator seed 42, 2026-10-16..2026-11-14. Run it only when asked ("run holdout").
  Every execution, failed ones included, is logged in data/eval/experiment_log.jsonl and counted in
  n_test_evaluations. Nothing from the holdout is used to choose k, guardrails, threshold or simulation settings.
  Writes data/eval/runs/{run_id}.json and data/eval/latest.json (GET /evaluation). Never edit by hand.

Conditions (ml/simulate.py): A always SALE, B naive rule, C model, D + payer memory, E full system.
Every condition uses the same model, threshold, k and simulated-answer stream. Merchants start with empty
memory and no configuration on 2026-10-16. Reversals are ignored in the replay.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import experiment_log
from .common import ARTIFACTS, GENERATED, REPO_ROOT
from .simulate import replay, simulated_answers
from .train import ece
from app.classifier import procedure  # noqa: E402
from app.classifier.features import FEATURES  # noqa: E402

SEED = 42
ANSWER_ERROR_RATE = 0.02
ANSWER_STREAM = 2026  # simulated-answer RNG stream: default_rng([SEED, ANSWER_STREAM])
TEST_MERCHANTS = [f"M{n}" for n in range(171, 281)]
TEST_PERIOD = (date(2026, 10, 16), date(2026, 11, 14))
WEEKS = [("Days 1–7", 0, 6), ("Days 8–14", 7, 13), ("Days 15–21", 14, 20), ("Days 22–30", 21, 29)]
CONDITIONS = ("A", "B", "C", "D", "E")
CONDITION_NAMES = {"A": "Always SALE", "B": "Naive rule (P2P + round ₹100 = FAMILY)", "C": "Model, no feedback",
                   "D": "Model + payer memory", "E": "Full system (payer memory + remember, guardrails)"}
OUT_DIR = REPO_ROOT / "data" / "eval"
BASELINE_FILE = OUT_DIR / "baseline" / "latest_model-freeze-1.json"


def _counted(count: int, of: int) -> dict:
    return {"count": int(count), "of": int(of), "rate": round(count / of, 4) if of else None}


# --- loading and scoring ----------------------------------------------------------------------------
def load_artifact(path: Path | None = None) -> tuple[dict, dict]:
    """(current.json-style info, artifact). path None = ml/artifacts/current.json."""
    if path is None:
        info = json.loads((ARTIFACTS / "current.json").read_text(encoding="utf-8"))
        path = REPO_ROOT / info["artifact"]
    art = joblib.load(path)
    info = {"model_version": art["model_version"], "threshold": float(art["threshold"]),
            "k": float(art.get("k", procedure.K)), "artifact": Path(path).relative_to(REPO_ROOT).as_posix()}
    return info, art


def test_window(feats: pd.DataFrame, merchants: list[str], period=TEST_PERIOD) -> pd.DataFrame:
    t = feats[feats.merchant_id.isin(merchants) & feats.date.between(period[0].isoformat(), period[1].isoformat())]
    return t.sort_values(["merchant_id", "timestamp", "transaction_id"]).reset_index(drop=True)


def score(art: dict, t: pd.DataFrame) -> np.ndarray:
    raw = art["model"].predict_proba(t[list(FEATURES)].to_numpy(float))[:, 1]
    return art["calibrator"].predict(raw)


# --- metrics -----------------------------------------------------------------------------------------
def metrics(d: pd.DataFrame, t: pd.DataFrame, cond: str, period=TEST_PERIOD) -> dict:
    truth = t.true_label.to_numpy()
    auto = (d.action == "AUTO_CLASSIFY").to_numpy()
    ask = ~auto
    sug, final, src, rule = d.suggested.to_numpy(), d.final.to_numpy(), d.source.to_numpy(), d.rule.to_numpy()
    n_merchants, n_days = t.merchant_id.nunique(), (period[1] - period[0]).days + 1
    day_idx = (pd.to_datetime(t.date) - pd.Timestamp(period[0])).dt.days.to_numpy()
    is_fam, is_sale = truth == "FAMILY", truth == "SALE"
    by_source = {}
    if cond in ("C", "D", "E"):
        for s in ("MODEL", "PAYER_MEMORY", "MERCHANT_CONFIG"):
            m = auto & (src == s)
            by_source[s] = {"correct": int((sug[m] == truth[m]).sum()), "of": int(m.sum()),
                            "precision": round(float((sug[m] == truth[m]).mean()), 4) if m.any() else None}
    weeks = []
    for _, lo, hi in WEEKS:
        w = (day_idx >= lo) & (day_idx <= hi)
        weeks.append(round(float(ask[w].sum()) / (n_merchants * (hi - lo + 1)), 2))
    cfg = auto & (src == "MERCHANT_CONFIG")
    cfg_family, cfg_customer = cfg & (rule == "CONFIGURED_FAMILY"), cfg & (rule == "CONFIGURED_CUSTOMER")
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
        "config_errors_by_list": {"FAMILY": _counted((cfg_family & (sug != truth)).sum(), cfg_family.sum()),
                                  "CUSTOMER": _counted((cfg_customer & (sug != truth)).sum(), cfg_customer.sum())},
        "guardrail_questions": {"FAMILY_GUARDRAIL": int((rule == "FAMILY_GUARDRAIL").sum()),
                                "CUSTOMER_GUARDRAIL": int((rule == "CUSTOMER_GUARDRAIL").sum())},
        "questions_per_day_by_week": weeks,
        "confusion_matrix_auto": {"labels": ["SALE", "FAMILY"], "rows": "true label", "columns": "decision",
                                  "matrix": [[int((auto & is_sale & (sug == "SALE")).sum()), int((auto & is_sale & (sug == "FAMILY")).sum())],
                                             [int((auto & is_fam & (sug == "SALE")).sum()), int((auto & is_fam & (sug == "FAMILY")).sum())]]},
    }


def headline(c: dict) -> dict:
    return {"family_money_found": c["family_recall_final"], "income_wrongly_removed": c["income_wrongly_removed"],
            "questions_per_merchant_per_day": c["questions_per_merchant_per_day"]}


def run_conditions(t: pd.DataFrame, q: np.ndarray, *, tau: float, k: float, answer_error: float = ANSWER_ERROR_RATE,
                   seed: int = SEED, conditions=CONDITIONS, period=TEST_PERIOD) -> dict:
    answers, remember = simulated_answers(t.true_label.to_numpy(), answer_error,
                                          np.random.default_rng([seed, ANSWER_STREAM]))
    return {c: metrics(replay(c, t, q, tau, answers, remember, k=k), t, c, period) for c in conditions}


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


# --- the final holdout ----------------------------------------------------------------------------------
def holdout() -> dict:
    info, art = load_artifact()
    tau, k = info["threshold"], info["k"]
    with experiment_log.logged_run(kind="holdout", dataset=experiment_log.HOLDOUT_DATASET,
                                   model_version=info["model_version"], k=k, threshold=tau,
                                   config={"answer_error": ANSWER_ERROR_RATE, "answer_seed": [SEED, ANSWER_STREAM],
                                           "remember_probability": 0.5}) as run:
        feats = pd.read_parquet(GENERATED / "features.parquet")
        t = test_window(feats, TEST_MERCHANTS)
        q = score(art, t)
        conditions = run_conditions(t, q, tau=tau, k=k)
        curve = curve_c(t, q)
        at_tau = next(c for c in curve if c["threshold"] == round(tau, 2))
        assert at_tau["coverage"] == conditions["C"]["coverage"], "vectorised curve disagrees with the replay"
        truth = t.true_label.to_numpy()
        ece_test, bins = ece(q, (truth == "FAMILY").astype(int))
        label_mix = json.loads((GENERATED / "label_mix.json").read_text(encoding="utf-8"))
        selection = art["threshold_selection"]
        pick = lambda c: {x: conditions[c][x] for x in ("precision_auto", "coverage",  # noqa: E731
                                                        "questions_per_merchant_per_day", "overall_accuracy")}
        baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8")) if BASELINE_FILE.exists() else None
        result = {
            "run_id": run["run_id"],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "data_label": f"Synthetic data (generator seed {label_mix['seed']})",
            "model_version": info["model_version"],
            "threshold": tau,
            "k": k,
            "n_test_evaluations": experiment_log.n_test_evaluations(),  # includes this run
            "split": {"train_merchants": 70, "test_merchants": len(TEST_MERCHANTS),
                      "test_period": f"{TEST_PERIOD[0]} to {TEST_PERIOD[1]}", "test_transactions": len(t)},
            "headline": {
                "note": "Show these first. precision_auto and precision by source are secondary and always shown "
                        "next to the always-SALE baseline (condition A).",
                "always_sale": headline(conditions["A"]), "baseline": headline(conditions["C"]),
                "with_feedback": headline(conditions["E"])},
            "previous_baseline": None if baseline is None else {
                "tag": "model-freeze-1", "run_id": baseline["run_id"], "model_version": baseline["model_version"],
                "threshold": baseline["threshold"], "headline": baseline.get("headline")},
            "threshold_selection": {x: selection[x] for x in ("set", "objective", "constraints", "tie_break",
                                                              "met_constraints", "chosen", "table")},
            "threshold_curve_calibration": [
                {"threshold": r["threshold"], "family_recall": r["family_recall"],
                 "questions_per_merchant_per_day": r["questions_per_merchant_per_day"],
                 "silent_errors": r["silent_errors"]["total"]} for r in selection["table"]],
            "k_selection": art.get("k_selection"),
            "baseline": pick("C"),
            "with_feedback": pick("E"),
            "questions_per_day_by_week": {"labels": [w[0] for w in WEEKS],
                                          "baseline": conditions["C"]["questions_per_day_by_week"],
                                          "with_feedback": conditions["E"]["questions_per_day_by_week"]},
            "pr_coverage_curve": curve,
            "confusion_matrix_auto": conditions["E"]["confusion_matrix_auto"],
            "calibration": {"ece": ece_test, "bins": bins},
            "merchant_answer_error_rate": ANSWER_ERROR_RATE,
            "label_mix": {"count_share": label_mix["count_share"], "value_share": label_mix["value_share"]},
            "conditions": conditions,
            "notes": {
                "family_metric_denominators": "family_recall_final: of all true FAMILY payments; silent_family_errors: "
                                              "of all true SALE payments; silent_sale_errors: of all true FAMILY payments; "
                                              "config_errors: of all MERCHANT_CONFIG decisions; income_wrongly_removed: "
                                              "true SALE payments whose final label is FAMILY (silent + merchant answer "
                                              "errors), of all true SALE payments.",
                "confusion_matrix_auto": "Top-level matrix is condition E (the full system); each condition has its own.",
                "reversals": "Ignored in the evaluation replay (0.1% of payments).",
                "remember": "Condition E: after a FAMILY answer, or a SALE answer on a P2P payment, the simulated "
                            "merchant chooses remember with probability 0.5. Guardrails apply.",
            },
            "seed": SEED,
            "git_commit": run["git_commit"],
        }
        run["result"] = {"headline_with_feedback": result["headline"]["with_feedback"]}
        runs = OUT_DIR / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        (runs / f"{run['run_id']}.json").write_text(text, encoding="utf-8")
        (OUT_DIR / "latest.json").write_text(text, encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holdout", action="store_true", help="run the FINAL holdout evaluation (only when asked)")
    args = ap.parse_args()
    if not args.holdout:
        raise SystemExit("This evaluates the final holdout (M171-M280, seed 42). Pass --holdout to run it, and only "
                         "after the go-ahead. For robustness runs use scripts/robustness.py.")
    r = holdout()
    for c, m in r["conditions"].items():
        print(f"{c} {m['name']:52s} precision_auto {m['precision_auto']}  coverage {m['coverage']}  "
              f"q/merchant/day {m['questions_per_merchant_per_day']}")
    print(f"-> {OUT_DIR / 'latest.json'}  (n_test_evaluations = {r['n_test_evaluations']})")


if __name__ == "__main__":
    main()
