"""Append-only experiment log: data/eval/experiment_log.jsonl.

One line per evaluation execution, written in a `finally` block, so failed and interrupted runs
(including Ctrl-C) are logged with status "failed". Only a hard kill (power loss, SIGKILL) escapes.
Lines are never edited or removed. n_test_evaluations() counts final-holdout executions ever started.
"""
from __future__ import annotations

import json
import subprocess
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from .common import REPO_ROOT

LOG = REPO_ROOT / "data" / "eval" / "experiment_log.jsonl"
HOLDOUT_KINDS = ("holdout", "adhoc_holdout_inspection")
HOLDOUT_DATASET = "holdout: M171-M280, generator seed 42, 2026-10-16..2026-11-14"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def append(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]


def n_test_evaluations() -> int:
    """Final-holdout executions ever started, including failed ones."""
    return sum(1 for r in read() if r.get("kind") in HOLDOUT_KINDS)


@contextmanager
def logged_run(*, kind: str, dataset: str, model_version: str | None, k: float | None, threshold: float | None,
               config: dict | None = None) -> Iterator[dict]:
    """with logged_run(...) as run: ... ; put extra result fields into run["result"]."""
    run = {"run_id": f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}", "kind": kind,
           "dataset": dataset, "model_version": model_version, "k": k, "threshold": threshold,
           "git_commit": _git_commit(), "config": config or {}, "start": _now(), "result": {}}
    status, error = "failed", None
    try:
        yield run
        status = "ok"
    except BaseException as exc:  # includes KeyboardInterrupt: partial runs are logged too
        error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
        raise
    finally:
        append({**run, "end": _now(), "status": status, "error": error})
