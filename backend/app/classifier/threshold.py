"""Effective AUTO threshold = max(model artifact threshold, CONF_THRESHOLD) (agreed 2026-11-14).

CONF_THRESHOLD can only make the system stricter than the trained model, never looser.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import REPO_ROOT

CURRENT_MODEL_FILE = REPO_ROOT / "ml" / "artifacts" / "current.json"


@dataclass(frozen=True)
class ModelInfo:
    model_version: str
    threshold: float


def current_model() -> ModelInfo | None:
    """Reads ml/artifacts/current.json ({"model_version", "threshold"}) written by ml.train.
    None until the first model is trained."""
    if not CURRENT_MODEL_FILE.exists():
        return None
    data = json.loads(CURRENT_MODEL_FILE.read_text(encoding="utf-8"))
    return ModelInfo(model_version=data["model_version"], threshold=float(data["threshold"]))


def effective_threshold(model_threshold: float | None, conf_threshold: float) -> float:
    if model_threshold is None:
        return conf_threshold
    return max(model_threshold, conf_threshold)
