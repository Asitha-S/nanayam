"""python -m scripts.robustness   (from the repository root, after python -m ml.train)

Robustness experiments. NEVER on the final holdout (M171-M280 of generator seed 42): every population here is
the evaluation-merchant group M171-M280 regenerated from ANOTHER generator seed. Four separate experiments,
reported separately; mean/min/max are taken only within one experiment.

  4a population: generator seeds 7, 13, 21, 99, 123; fixed current model; conditions C and E
  4b training:   fixed population (seed 7); full training pipeline retrained with LightGBM seed i and
                 merchant-fold assignment i, i = 1..5 (tau and k re-selected on the calibration set); C and E
  4c answers:    population seed 7, fixed model; merchant answer error 2%, 5%, 10%; condition E
  4d family:     fixed model; population seed 7 regenerated with family and friend transfer rates x0.5 and x4
                 (intervals x2 and /4; same number of family/friend payers; customer behaviour unchanged)

Writes data/eval/robustness.json; every evaluation execution is logged in data/eval/experiment_log.jsonl.
Time budget: if the projected total exceeds 60 minutes, 4a uses seeds 7, 13, 21 and 4b folds 1-3 (reported).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

from data.generator.generate import generate
from ml import experiment_log
from ml.common import GENERATED, REPO_ROOT
from ml.evaluate import TEST_MERCHANTS, TEST_PERIOD, load_artifact, run_conditions, score, test_window
from ml.featurize import featurize_frames
from ml.train import fit_pipeline

HOLDOUT_GENERATOR_SEED = 42
POP_SEEDS = [7, 13, 21, 99, 123]
POP_SEEDS_REDUCED = [7, 13, 21]
TRAIN_SEEDS = [1, 2, 3, 4, 5]
TRAIN_SEEDS_REDUCED = [1, 2, 3]
FIXED_POPULATION = 7
ANSWER_ERRORS = [0.02, 0.05, 0.10]
FAMILY_RATES = [0.5, 4.0]
BUDGET_SECONDS = 60 * 60
OUT = REPO_ROOT / "data" / "eval" / "robustness.json"

_populations: dict = {}


def population(gen_seed: int, family_rate: float = 1.0) -> tuple[pd.DataFrame, dict, float]:
    """(test-window frame, realised label mix, seconds to build). Cached per (seed, rate)."""
    if gen_seed == HOLDOUT_GENERATOR_SEED:
        raise SystemExit("Refusing: generator seed 42 M171-M280 is the final holdout")
    key = (gen_seed, family_rate)
    if key not in _populations:
        start = time.monotonic()
        gen = generate(gen_seed, only=TEST_MERCHANTS, family_rate=family_rate)
        feats = featurize_frames(gen.merchants, gen.payments, gen.labels, TEST_MERCHANTS)
        t = test_window(feats, TEST_MERCHANTS)
        mix = {}
        for name, part in (("all_dates", feats), ("test_window", t)):
            fam = part[part.true_label == "FAMILY"]
            mix[name] = {"payments": int(len(part)), "family_payments": int(len(fam)),
                         "count_share": round(len(fam) / len(part), 6),
                         "value_share": round(int(fam.amount_paise.sum()) / int(part.amount_paise.sum()), 6)}
        _populations[key] = (t, mix, time.monotonic() - start)
    return _populations[key]


def summary(c: dict) -> dict:
    return {
        "family_money_found": c["family_recall_final"],
        "income_wrongly_removed": c["income_wrongly_removed"],
        "questions_per_merchant_per_day": c["questions_per_merchant_per_day"],
        "precision_auto": c["precision_auto"],
        "precision_auto_by_source": c["precision_auto_by_source"],
        "coverage": c["coverage"],
        "silent_family_errors": c["silent_family_errors"],
        "silent_sale_errors": c["silent_sale_errors"],
        "config_errors": c["config_errors"],
        "config_errors_by_list": c["config_errors_by_list"],
        "guardrail_questions": c["guardrail_questions"],
    }


def evaluate_run(experiment: str, *, gen_seed: int, family_rate: float, answer_error: float, conditions: tuple,
                 model: dict, info: dict, extra: dict | None = None) -> dict:
    t, mix, _ = population(gen_seed, family_rate)
    dataset = (f"robustness population: M171-M280 regenerated with generator seed {gen_seed}, family rate "
               f"x{family_rate}, {TEST_PERIOD[0]}..{TEST_PERIOD[1]}")
    config = {"experiment": experiment, "generator_seed": gen_seed, "family_rate": family_rate,
              "answer_error": answer_error, "conditions": list(conditions), **(extra or {})}
    with experiment_log.logged_run(kind="robustness", dataset=dataset, model_version=info["model_version"],
                                   k=info["k"], threshold=info["threshold"], config=config) as run:
        q = score(model, t)
        res = run_conditions(t, q, tau=info["threshold"], k=info["k"], answer_error=answer_error,
                             conditions=conditions)
        run["result"] = {c: {"family_found": res[c]["family_recall_final"]["count"],
                             "income_wrongly_removed": res[c]["income_wrongly_removed"]["count"]} for c in conditions}
    return {"experiment": experiment, "run_id": run["run_id"], **config, "model_version": info["model_version"],
            "k": info["k"], "threshold": info["threshold"], "test_transactions": int(len(t)), "label_mix": mix,
            "conditions": {c: summary(res[c]) for c in conditions}}


def _stats(values: list[float]) -> dict:
    return {"mean": round(float(np.mean(values)), 4), "min": round(float(np.min(values)), 4),
            "max": round(float(np.max(values)), 4)}


def experiment_summary(runs: list[dict]) -> dict:
    """mean/min/max over the runs of ONE experiment."""
    out = {}
    for cond in runs[0]["conditions"]:
        rows = [r["conditions"][cond] for r in runs]
        out[cond] = {
            "family_money_found_rate": _stats([x["family_money_found"]["rate"] for x in rows]),
            "family_money_found_count": _stats([x["family_money_found"]["count"] for x in rows]),
            "income_wrongly_removed_count": _stats([x["income_wrongly_removed"]["count"] for x in rows]),
            "silent_family_errors_count": _stats([x["silent_family_errors"]["count"] for x in rows]),
            "silent_sale_errors_count": _stats([x["silent_sale_errors"]["count"] for x in rows]),
            "config_errors_count": _stats([x["config_errors"]["count"] for x in rows]),
            "questions_per_merchant_per_day": _stats([x["questions_per_merchant_per_day"] for x in rows]),
            "precision_auto": _stats([x["precision_auto"] for x in rows]),
            "coverage": _stats([x["coverage"] for x in rows]),
        }
    return out


def run_4d(model: dict, info: dict) -> dict:
    runs = [evaluate_run("4d_family_frequency", gen_seed=FIXED_POPULATION, family_rate=r, answer_error=0.02,
                         conditions=("C", "E"), model=model, info=info) for r in FAMILY_RATES]
    return {
        "description": f"fixed model; population seed {FIXED_POPULATION} regenerated with family and friend transfer "
                       f"rates x{FAMILY_RATES} (intervals x2 / /4; same payers; customers, their refunds and "
                       f"reversals unchanged; reversals of family transfers dropped); conditions C and E",
        "reference_family_rate_1": population(FIXED_POPULATION)[1],
        "runs": runs, "summary": experiment_summary(runs)}


def rerun_4d(reason: str) -> None:
    """Replace experiment 4d in robustness.json; the superseded runs stay in the experiment log."""
    t0 = time.monotonic()
    info, art = load_artifact()
    model = {"model": art["model"], "calibrator": art["calibrator"]}
    result = json.loads(OUT.read_text(encoding="utf-8"))
    old = result["experiments"]["4d_family_frequency"]
    superseded = [r["run_id"] for r in old["runs"]]
    experiment_log.append({"kind": "note", "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                           "superseded_run_ids": superseded, "reason": reason})
    new = run_4d(model, info)
    new["superseded"] = {"run_ids": superseded, "reason": reason}
    result["experiments"]["4d_family_frequency"] = new
    result["runtime_seconds"]["4d_family_frequency_rerun"] = round(time.monotonic() - t0)
    result["git_commit_4d_rerun"] = experiment_log._git_commit()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {OUT}  4d rerun {result['runtime_seconds']['4d_family_frequency_rerun']} s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["4d"], help="rerun one experiment and replace it in robustness.json")
    ap.add_argument("--reason", default="", help="why an experiment is rerun (logged)")
    args = ap.parse_args()
    if args.only == "4d":
        return rerun_4d(args.reason or "rerun")
    t0 = time.monotonic()
    info, art = load_artifact()
    model = {"model": art["model"], "calibrator": art["calibrator"]}
    runtimes: dict = {}

    # projection from the first population (generation + features dominate)
    _, _, build_s = population(FIXED_POPULATION)
    probe = time.monotonic()
    evaluate_run("probe", gen_seed=FIXED_POPULATION, family_rate=1.0, answer_error=0.02, conditions=("C", "E"),
                 model=model, info=info, extra={"note": "timing probe for the 60-minute budget; not reported"})
    eval_s = time.monotonic() - probe
    train_s = 60.0  # measured release-pipeline training time on this machine (step 2)
    projected = (len(POP_SEEDS) + len(FAMILY_RATES)) * build_s + (len(POP_SEEDS) + 5 + 3 + 2) * eval_s + 5 * train_s
    reduced = projected > BUDGET_SECONDS
    pop_seeds = POP_SEEDS_REDUCED if reduced else POP_SEEDS
    train_seeds = TRAIN_SEEDS_REDUCED if reduced else TRAIN_SEEDS
    print(f"population build {build_s:.0f} s, evaluation {eval_s:.0f} s -> projected {projected / 60:.1f} min"
          f"{' (over budget: reduced set)' if reduced else ''}")

    experiments: dict = {}
    s = time.monotonic()
    runs = [evaluate_run("4a_population", gen_seed=g, family_rate=1.0, answer_error=0.02, conditions=("C", "E"),
                         model=model, info=info) for g in pop_seeds]
    experiments["4a_population"] = {"description": "fixed current model; populations from generator seeds "
                                    f"{pop_seeds}; conditions C and E", "runs": runs, "summary": experiment_summary(runs)}
    runtimes["4a_population"] = round(time.monotonic() - s)

    s = time.monotonic()
    train_df = pd.read_parquet(GENERATED / "features.parquet")  # seed-42 training merchants only are used
    runs = []
    for i in train_seeds:
        fitted = fit_pipeline(train_df, seed=i, fold_seed=i)
        runs.append(evaluate_run("4b_training", gen_seed=FIXED_POPULATION, family_rate=1.0, answer_error=0.02,
                                 conditions=("C", "E"), model=fitted,
                                 info={"model_version": fitted["model_version"], "threshold": fitted["threshold"],
                                       "k": fitted["k"]},
                                 extra={"lightgbm_seed": i, "fold_assignment_seed": i,
                                        "tau_met_constraints": fitted["met_constraints"]}))
    experiments["4b_training"] = {"description": f"population seed {FIXED_POPULATION}; retrained with LightGBM seed and "
                                  f"fold assignment {train_seeds} (tau and k re-selected); conditions C and E",
                                  "runs": runs, "summary": experiment_summary(runs)}
    runtimes["4b_training"] = round(time.monotonic() - s)

    s = time.monotonic()
    runs = [evaluate_run("4c_answer_error", gen_seed=FIXED_POPULATION, family_rate=1.0, answer_error=e,
                         conditions=("E",), model=model, info=info) for e in ANSWER_ERRORS]
    experiments["4c_answer_error"] = {"description": f"population seed {FIXED_POPULATION}, fixed model; answer error "
                                      f"{ANSWER_ERRORS}; condition E", "runs": runs, "summary": experiment_summary(runs)}
    runtimes["4c_answer_error"] = round(time.monotonic() - s)

    s = time.monotonic()
    experiments["4d_family_frequency"] = run_4d(model, info)
    runtimes["4d_family_frequency"] = round(time.monotonic() - s)

    result = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": experiment_log._git_commit(),
        "holdout_excluded": "M171-M280 of generator seed 42 is never used here",
        "model": info,
        "reduced_for_time_budget": reduced,
        "projected_minutes": round(projected / 60, 1),
        "runtime_seconds": {**runtimes, "total": round(time.monotonic() - t0)},
        "experiments": experiments,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {OUT}  runtime {result['runtime_seconds']}")


if __name__ == "__main__":
    main()
