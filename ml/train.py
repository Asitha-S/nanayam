"""python -m ml.train   (after python -m data.generator.run --seed 42)

DATA_AND_LOGIC 5.2-5.4 (calibration and threshold objective as agreed 2026-11-14):
- Model: LightGBM binary classifier, target FAMILY, class_weight balanced.
  Final model: M101-M170, payments 2026-08-01..2026-10-01.
- Calibration: isotonic regression fitted on OUT-OF-FOLD raw scores over the whole train + calibration
  period (M101-M170, 2026-08-01..2026-10-15). 5 folds grouped by merchant; each fold model is trained
  like the final model (train period) on the other merchants and scores the held-out merchants.
- Threshold: on the calibration set only (M101-M170, 2026-10-02..2026-10-15), condition C rules (no
  feedback), merchant answers taken as correct. Choose tau minimising silent errors (family counted as
  sale + sale removed as family) subject to questions <= 1.0 per merchant per day, precision_auto >= 0.95
  and tau >= CONF_THRESHOLD. Ties: lower tau (fewer questions).
Writes ml/artifacts/{model_version}.joblib (with the full calibration-set table) and ml/artifacts/current.json.
Test merchants (M171-M280) are never touched.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from .common import ARTIFACTS, GENERATED, REPO_ROOT
from .featurize import OUT as FEATURES_FILE, featurize
from app.classifier import procedure  # noqa: E402
from app.classifier.features import FEATURES  # noqa: E402

SEED = 42
TRAIN_MERCHANTS = {f"M{n}" for n in range(101, 171)}
TRAIN_DATES = ("2026-08-01", "2026-10-01")
CALIB_DATES = ("2026-10-02", "2026-10-15")
OOF_DATES = (TRAIN_DATES[0], CALIB_DATES[1])
N_FOLDS = 5
TAU_GRID = [round(0.80 + i / 100, 2) for i in range(20)] + [0.995, 0.998, 0.999]
MIN_PRECISION = 0.95
MAX_QUESTIONS_PER_MERCHANT_DAY = 1.0
PARAMS = dict(num_leaves=31, learning_rate=0.05, n_estimators=400, min_child_samples=40, class_weight="balanced")


def new_model() -> LGBMClassifier:
    return LGBMClassifier(**PARAMS, random_state=SEED, deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1)


def xy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return df[list(FEATURES)].to_numpy(float), (df.true_label == "FAMILY").to_numpy(int)


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    """Expected calibration error with equal-width bins."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total, out = 0.0, []
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
            out.append({"p_mean": round(float(p[m].mean()), 4), "accuracy": round(float(y[m].mean()), 4),
                        "count": int(m.sum())})
    return round(float(total), 4), out


def out_of_fold_scores(period: pd.DataFrame) -> np.ndarray:
    """Raw scores for every row of `period`, each from a model that never saw that row's merchant."""
    raw = np.full(len(period), np.nan)
    groups = period.merchant_id.to_numpy()
    for k, (_, held_idx) in enumerate(GroupKFold(n_splits=N_FOLDS).split(period, groups=groups)):
        held = set(groups[held_idx])
        fit_rows = period[~period.merchant_id.isin(held) & period.date.between(*TRAIN_DATES)]
        model = new_model().fit(*xy(fit_rows))
        raw[held_idx] = model.predict_proba(period.iloc[held_idx][list(FEATURES)].to_numpy(float))[:, 1]
        print(f"  fold {k + 1}/{N_FOLDS}: {len(held)} held-out merchants, fit on {len(fit_rows):,} rows")
    assert not np.isnan(raw).any()
    return raw


def selection_table(calib: pd.DataFrame, q: np.ndarray, taus: list[float]) -> list[dict]:
    """Condition C on the calibration set, merchant answers taken as correct (used only to choose tau)."""
    truth = calib.true_label.to_numpy()
    new, amounts = calib.is_new_payer.to_numpy() > 0, calib.amount_paise.to_numpy()
    ptype = calib.is_p2p.map(lambda x: "P2P" if x else "P2M").to_numpy()
    merchant_days = calib.merchant_id.nunique() * calib.date.nunique()
    n_family = int((truth == "FAMILY").sum())
    rows = []
    for tau in taus:
        auto = correct = family_as_sale = sale_as_family = family_found = 0
        for i in range(len(calib)):
            o = procedure.run(q=float(q[i]), n_family=0, n_sale=0, is_new_payer=bool(new[i]),
                              amount_paise=int(amounts[i]), payment_type=ptype[i], tau=tau)
            if o.action == "AUTO_CLASSIFY":
                auto += 1
                correct += o.suggested == truth[i]
                family_as_sale += truth[i] == "FAMILY" and o.suggested == "SALE"
                sale_as_family += truth[i] == "SALE" and o.suggested == "FAMILY"
                family_found += truth[i] == "FAMILY" and o.suggested == "FAMILY"
            else:
                family_found += truth[i] == "FAMILY"  # asked and answered
        asked = len(calib) - auto
        rows.append({
            "threshold": tau,
            "coverage": round(auto / len(calib), 4),
            "precision_auto": round(correct / auto, 4) if auto else None,
            "questions_per_merchant_per_day": round(asked / merchant_days, 3),
            "silent_errors": {"family_counted_as_sale": int(family_as_sale), "sale_removed_as_family": int(sale_as_family),
                              "total": int(family_as_sale + sale_as_family)},
            "family_recall": {"count": int(family_found), "of": n_family,
                              "rate": round(family_found / n_family, 4) if n_family else None},
        })
    return rows


def choose_tau(table: list[dict], conf_threshold: float) -> tuple[float, bool]:
    ok = [r for r in table
          if r["threshold"] >= conf_threshold and r["questions_per_merchant_per_day"] <= MAX_QUESTIONS_PER_MERCHANT_DAY
          and r["precision_auto"] is not None and r["precision_auto"] >= MIN_PRECISION]
    if not ok:
        return max(r["threshold"] for r in table), False
    best = min(ok, key=lambda r: (r["silent_errors"]["total"], r["threshold"]))
    return best["threshold"], True


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    df = featurize()
    df.to_parquet(FEATURES_FILE, index=False)
    mine = df[df.merchant_id.isin(TRAIN_MERCHANTS)].reset_index(drop=True)
    train = mine[mine.date.between(*TRAIN_DATES)]
    calib = mine[mine.date.between(*CALIB_DATES)].reset_index(drop=True)
    period = mine[mine.date.between(*OOF_DATES)].reset_index(drop=True)
    X, y = xy(train)
    print(f"train {len(train):,} rows ({y.sum()} FAMILY); out-of-fold period {len(period):,} rows "
          f"({(period.true_label == 'FAMILY').sum()} FAMILY); calibration set {len(calib):,} rows "
          f"({(calib.true_label == 'FAMILY').sum()} FAMILY)")

    print("out-of-fold scores for calibration:")
    raw_oof = out_of_fold_scores(period)
    y_oof = (period.true_label == "FAMILY").to_numpy(int)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_oof, y_oof)
    ece_oof_raw, _ = ece(raw_oof, y_oof)
    ece_oof_cal, oof_bins = ece(calibrator.predict(raw_oof), y_oof)

    model = new_model().fit(X, y)
    q_calib = calibrator.predict(model.predict_proba(xy(calib)[0])[:, 1])

    conf_threshold = float(os.getenv("CONF_THRESHOLD", "0.90"))
    table = selection_table(calib, q_calib, TAU_GRID)
    tau, met = choose_tau(table, conf_threshold)
    chosen = next(r for r in table if r["threshold"] == tau)

    buf = io.BytesIO()
    joblib.dump((model, calibrator), buf)
    version = f"clf-{datetime.now().strftime('%Y%m%d')}-{hashlib.sha256(buf.getvalue()).hexdigest()[:6]}"
    artifact = {
        "model_version": version, "model": model, "calibrator": calibrator, "features": list(FEATURES),
        "threshold": tau, "params": PARAMS, "seed": SEED, "git_commit": _git_commit(),
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "train": {"merchants": "M101-M170", "dates": TRAIN_DATES, "rows": len(train), "family": int(y.sum())},
        "calibration": {"method": f"isotonic on out-of-fold scores, {N_FOLDS} folds grouped by merchant",
                        "dates": OOF_DATES, "rows": len(period), "family": int(y_oof.sum()),
                        "ece_raw_oof": ece_oof_raw, "ece_calibrated_oof": ece_oof_cal, "bins_oof": oof_bins},
        "threshold_selection": {
            "set": f"M101-M170, {CALIB_DATES[0]}..{CALIB_DATES[1]}, condition C rules, answers taken as correct",
            "objective": "minimise silent errors (family counted as sale + sale removed as family)",
            "constraints": {"max_questions_per_merchant_per_day": MAX_QUESTIONS_PER_MERCHANT_DAY,
                            "min_precision_auto": MIN_PRECISION, "min_threshold": conf_threshold},
            "tie_break": "lower threshold", "met_constraints": met, "chosen": chosen, "table": table},
        "label_mix": json.loads((GENERATED / "label_mix.json").read_text(encoding="utf-8")),
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for old in ARTIFACTS.glob("clf-*.joblib"):
        old.unlink()  # one model at a time; the previous one is in git history
    path = ARTIFACTS / f"{version}.joblib"
    joblib.dump(artifact, path, compress=3)
    (ARTIFACTS / "current.json").write_text(json.dumps(
        {"model_version": version, "threshold": tau, "artifact": path.relative_to(REPO_ROOT).as_posix()}, indent=2)
        + "\n", encoding="utf-8")

    print(f"model {version} -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"out-of-fold ECE: raw {ece_oof_raw} -> calibrated {ece_oof_cal}")
    print(f"threshold {tau} ({'constraints met' if met else 'NO tau met the constraints; using the highest'})")
    print("  tau    coverage  precision  q/merchant/day  silent(fam->sale, sale->fam)  family recall")
    for r in table:
        mark = " <" if r["threshold"] == tau else ""
        s = r["silent_errors"]
        print(f"  {r['threshold']:<6} {r['coverage']:<9} {r['precision_auto']!s:<10} {r['questions_per_merchant_per_day']:<15} "
              f"{s['total']:>3} ({s['family_counted_as_sale']}, {s['sale_removed_as_family']})"
              f"{'':17}{r['family_recall']['count']} of {r['family_recall']['of']}{mark}")


if __name__ == "__main__":
    main()
