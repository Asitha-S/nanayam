"""python -m ml.train   (after python -m data.generator.run --seed 42)

DATA_AND_LOGIC 5.2-5.4:
- LightGBM binary classifier, target FAMILY, class_weight balanced. Train: M101-M170, 2026-08-01..2026-10-01.
- Isotonic calibration on M101-M170, 2026-10-02..2026-10-15 (not used in fitting) -> q_model.
- Threshold: smallest tau in {0.80..0.99} whose precision_auto on the calibration set, using the full
  decision procedure without feedback (condition C), is >= 0.95, and never below CONF_THRESHOLD.
Writes ml/artifacts/{model_version}.joblib and ml/artifacts/current.json. Test merchants are never touched.
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

from .common import ARTIFACTS, GENERATED, REPO_ROOT
from .featurize import OUT as FEATURES_FILE, featurize
from app.classifier import procedure  # noqa: E402
from app.classifier.features import FEATURES  # noqa: E402

SEED = 42
TRAIN_MERCHANTS = {f"M{n}" for n in range(101, 171)}
TRAIN_DATES = ("2026-08-01", "2026-10-01")
CALIB_DATES = ("2026-10-02", "2026-10-15")
TAU_GRID = [round(0.80 + i / 100, 2) for i in range(20)]
TARGET_PRECISION = 0.95
PARAMS = dict(num_leaves=31, learning_rate=0.05, n_estimators=400, min_child_samples=40, class_weight="balanced")


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    """Expected calibration error with equal-width bins."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total, out = 0.0, []
    for b in range(bins):
        m = idx == b
        if m.any():
            gap = abs(p[m].mean() - y[m].mean())
            total += m.mean() * gap
            out.append({"p_mean": round(float(p[m].mean()), 4), "accuracy": round(float(y[m].mean()), 4),
                        "count": int(m.sum())})
    return round(float(total), 4), out


def condition_c_curve(df: pd.DataFrame, q: np.ndarray, taus: list[float]) -> list[dict]:
    """precision_auto and coverage per tau, full decision procedure, no feedback, no configuration."""
    truth = df.true_label.to_numpy()
    new = df.is_new_payer.to_numpy() > 0
    amounts = df.amount_paise.to_numpy()
    curve = []
    for tau in taus:
        auto = correct = 0
        for i in range(len(df)):
            o = procedure.run(q=float(q[i]), n_family=0, n_sale=0, configured=False, is_new_payer=bool(new[i]),
                              amount_paise=int(amounts[i]), tau=tau)
            if o.action == "AUTO_CLASSIFY":
                auto += 1
                correct += o.suggested == truth[i]
        curve.append({"threshold": tau, "precision_auto": round(correct / auto, 4) if auto else None,
                      "coverage": round(auto / len(df), 4), "auto": auto})
    return curve


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    df = featurize()
    df.to_parquet(FEATURES_FILE, index=False)
    mine = df[df.merchant_id.isin(TRAIN_MERCHANTS)]
    train = mine[mine.date.between(*TRAIN_DATES)]
    calib = mine[mine.date.between(*CALIB_DATES)]
    X, y = train[list(FEATURES)].to_numpy(float), (train.true_label == "FAMILY").to_numpy(int)
    Xc, yc = calib[list(FEATURES)].to_numpy(float), (calib.true_label == "FAMILY").to_numpy(int)
    print(f"train {len(train):,} rows ({y.sum()} FAMILY), calibration {len(calib):,} rows ({yc.sum()} FAMILY)")

    model = LGBMClassifier(**PARAMS, random_state=SEED, deterministic=True, force_row_wise=True, n_jobs=1,
                           verbose=-1)
    model.fit(X, y)
    raw_c = model.predict_proba(Xc)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_c, yc)
    q_c = calibrator.predict(raw_c)
    ece_raw, _ = ece(raw_c, yc)
    ece_cal, bins = ece(q_c, yc)

    conf_threshold = float(os.getenv("CONF_THRESHOLD", "0.90"))
    curve = condition_c_curve(calib, q_c, TAU_GRID)
    ok = [c["threshold"] for c in curve
          if c["threshold"] >= conf_threshold and c["precision_auto"] is not None and c["precision_auto"] >= TARGET_PRECISION]
    tau = min(ok) if ok else max(TAU_GRID)

    buf = io.BytesIO()
    joblib.dump((model, calibrator), buf)
    version = f"clf-{datetime.now().strftime('%Y%m%d')}-{hashlib.sha256(buf.getvalue()).hexdigest()[:6]}"
    artifact = {
        "model_version": version, "model": model, "calibrator": calibrator, "features": list(FEATURES),
        "threshold": tau, "params": PARAMS, "seed": SEED, "git_commit": _git_commit(),
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "train": {"merchants": "M101-M170", "dates": TRAIN_DATES, "rows": len(train), "family": int(y.sum())},
        "calibration": {"dates": CALIB_DATES, "rows": len(calib), "family": int(yc.sum()), "ece_raw": ece_raw,
                        "ece_calibrated": ece_cal, "bins": bins},
        "threshold_selection": {"target_precision": TARGET_PRECISION, "conf_threshold": conf_threshold,
                                "curve": curve, "met_target": bool(ok)},
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
    print(f"ECE on calibration set: raw {ece_raw} -> calibrated {ece_cal}")
    print(f"threshold {tau} (target precision_auto >= {TARGET_PRECISION}, floor CONF_THRESHOLD {conf_threshold}"
          f"{'' if ok else '; TARGET NOT MET, using the highest tau'})")
    for c in curve:
        if c["threshold"] >= conf_threshold - 0.05:
            print(f"  tau {c['threshold']:.2f}  precision_auto {c['precision_auto']}  coverage {c['coverage']}")
    imp = sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1])[:8]
    print("top features (split count): " + ", ".join(f"{n} {v}" for n, v in imp))


if __name__ == "__main__":
    main()
