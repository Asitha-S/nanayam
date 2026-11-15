"""The trained classifier: LightGBM raw score -> isotonic calibration -> q_model = calibrated p(FAMILY)."""
from __future__ import annotations

from functools import lru_cache

import joblib
import numpy as np

from .. import errors
from .features import FEATURES
from .threshold import current_model


@lru_cache(maxsize=2)
def _load(path: str, mtime: float) -> dict:
    artifact = joblib.load(path)
    if tuple(artifact["features"]) != FEATURES:
        raise RuntimeError(f"Model {artifact['model_version']} was trained on different features; retrain.")
    return artifact


def artifact() -> dict:
    info = current_model()
    if info is None or not info.artifact.exists():
        raise errors.ApiError(500, "INTERNAL_ERROR", "No trained model. Run python -m ml.train.")
    return _load(str(info.artifact), info.artifact.stat().st_mtime)


def q_model(vector: list[float]) -> float:
    a = artifact()
    raw = a["model"].predict_proba(np.asarray([vector], dtype=float))[:, 1]
    return float(a["calibrator"].predict(raw)[0])
