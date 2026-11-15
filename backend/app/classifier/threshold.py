"""Current model artifact and the effective AUTO threshold.

ml/artifacts/current.json = {"model_version", "threshold", "artifact"} is written by `python -m ml.train`.
Effective threshold = max(model artifact threshold, CONF_THRESHOLD) (agreed 2026-11-14): CONF_THRESHOLD
can only make the system stricter than the trained model, never looser.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import REPO_ROOT

CURRENT_MODEL_FILE = REPO_ROOT / "ml" / "artifacts" / "current.json"


@dataclass(frozen=True)
class ModelInfo:
    model_version: str
    threshold: float
    artifact: Path


def current_model() -> ModelInfo | None:
    if not CURRENT_MODEL_FILE.exists():
        return None
    data = json.loads(CURRENT_MODEL_FILE.read_text(encoding="utf-8"))
    return ModelInfo(model_version=data["model_version"], threshold=float(data["threshold"]),
                     artifact=REPO_ROOT / data["artifact"])


def effective_threshold(model_threshold: float | None, conf_threshold: float) -> float:
    if model_threshold is None:
        return conf_threshold
    return max(model_threshold, conf_threshold)
