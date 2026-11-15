"""python -m scripts.release_gate   (from the repository root)

The release gate (DATA_AND_LOGIC 3.6) from a fresh database, step by step with a hard stop: the first failing
step ends the gate with a non-zero exit. Each step's output goes to logs/release_gate/<step>.log. A summary
table with per-step runtimes is printed, and on success written into data/demo/seed_meta.json ("release_gate").

Steps: clean -> generator -> generator_identity -> train -> seed -> notice_amount -> seed_checks -> tests
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
LOGS = REPO / "logs" / "release_gate"
BASELINE = REPO / "data" / "eval" / "baseline" / "generator_seed42_hashes.json"
SEED_DB = REPO / "data" / "demo" / "seed.db"
SEED_META = REPO / "data" / "demo" / "seed_meta.json"
GENERATED_FILES_TO_REMOVE = [SEED_DB, SEED_META, REPO / "backend" / "naanayam.db"]  # generated files only
EXPECTED_NOTICE_PAISE = 84_216_200  # ₹8,42,162


class GateFailure(Exception):
    pass


def run_module(step: str, args: list[str], timeout: int) -> str:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{step}.log"
    try:
        proc = subprocess.run([PY, "-m", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired as exc:
        log.write_text(f"TIMEOUT after {timeout} s\n{exc.stdout or ''}\n{exc.stderr or ''}", encoding="utf-8")
        raise GateFailure(f"timed out after {timeout} s (log: {log})") from exc
    log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:])
        raise GateFailure(f"exit {proc.returncode} (log: {log})\n{tail}")
    return proc.stdout


# --- steps -----------------------------------------------------------------------------------------
def clean() -> str:
    removed = []
    for f in GENERATED_FILES_TO_REMOVE:
        if f.exists():
            f.unlink()
            removed.append(f.relative_to(REPO).as_posix())
    return f"removed {removed or 'nothing'}"


def generator() -> str:
    run_module("generator", ["data.generator.run", "--seed", "42"], timeout=900)
    return "seed 42"


def generator_identity() -> str:
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    bad = [n for n, h in base["parquet_sha256"].items()
           if hashlib.sha256((REPO / "data" / "generated" / n).read_bytes()).hexdigest() != h]
    if bad:
        raise GateFailure(f"seed-42 generator output differs from model-freeze-1: {bad}")
    for f in ("M001_demo_day.json", "M002_demo_day.json"):
        old = subprocess.run(["git", "show", f"model-freeze-1:data/demo/{f}"], cwd=REPO, capture_output=True,
                             encoding="utf-8").stdout
        if json.loads((REPO / "data" / "demo" / f).read_text(encoding="utf-8")) != json.loads(old):
            raise GateFailure(f"{f} differs from model-freeze-1")
    return f"{len(base['parquet_sha256'])} parquet files and both demo scripts byte-identical to model-freeze-1"


def train() -> str:
    out = run_module("train", ["ml.train"], timeout=1800)
    current = json.loads((REPO / "ml" / "artifacts" / "current.json").read_text(encoding="utf-8"))
    reused = "reusing it" in out
    return f"{current['model_version']} (tau {current['threshold']}, k {current['k']}){' reused' if reused else ''}"


def seed() -> str:
    run_module("seed", ["data.seed_demo"], timeout=3600)
    return f"{SEED_DB.stat().st_size / 1e6:.1f} MB"


def notice_amount() -> str:
    n = json.loads((REPO / "data" / "demo" / "notice_numbers.json").read_text(encoding="utf-8"))
    if n["amount_questioned_paise"] != EXPECTED_NOTICE_PAISE:
        raise GateFailure(f"notice amount {n['amount_questioned_display']} != ₹8,42,162")
    return n["amount_questioned_display"]


def seed_checks() -> str:
    conn = sqlite3.connect(f"file:{SEED_DB.as_posix()}?mode=ro", uri=True)
    try:
        open_q = conn.execute(
            "SELECT p.timestamp FROM questions q JOIN payments p USING (transaction_id) WHERE q.status = 'OPEN'").fetchall()
        dates = sorted(r[0][:10] for r in open_q)
        if dates != ["2026-10-29", "2026-10-30", "2026-10-31"]:
            raise GateFailure(f"OPEN questions {dates}, expected exactly 3 on 29-31 Oct")
        answers = conn.execute(
            "SELECT f.confirmed_category FROM feedback f WHERE f.payer_id = 'P90003' AND f.feedback_id ="
            " (SELECT MAX(f2.feedback_id) FROM feedback f2 WHERE f2.transaction_id = f.transaction_id)").fetchall()
        n_family = sum(a[0] == "FAMILY" for a in answers)
        n_sale = len(answers) - n_family
        configured = conn.execute(
            "SELECT 1 FROM merchant_family_payers WHERE payer_id = 'P90003'"
            " UNION SELECT 1 FROM merchant_customer_payers WHERE payer_id = 'P90003'").fetchone()
        n = n_family + n_sale
        if configured or n < 3 or min(n_family, n_sale) / n < 0.25:
            raise GateFailure(f"Selvi is not MIXED (family {n_family}, sale {n_sale}, configured {bool(configured)})")
    finally:
        conn.close()
    return f"3 OPEN questions on 29-31 Oct; Selvi MIXED ({n_family} family / {n_sale} sale answers)"


def tests() -> str:
    out = run_module("tests", ["pytest", "-q", "-p", "no:cacheprovider"], timeout=3600)
    return out.strip().splitlines()[-1] if out.strip() else "no output"


STEPS = [("clean", clean), ("generator", generator), ("generator_identity", generator_identity), ("train", train),
         ("seed", seed), ("notice_amount", notice_amount), ("seed_checks", seed_checks), ("tests", tests)]


def main() -> int:
    rows, failed = [], None
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    for name, fn in STEPS:
        t = time.monotonic()
        try:
            detail, status = fn(), "ok"
        except GateFailure as exc:
            detail, status, failed = str(exc), "FAILED", name
        rows.append({"step": name, "status": status, "seconds": round(time.monotonic() - t, 1), "detail": detail})
        if failed:
            break
    print(f"\n{'step':20s} {'status':7s} {'seconds':>8s}  detail")
    for r in rows:
        print(f"{r['step']:20s} {r['status']:7s} {r['seconds']:>8.1f}  {r['detail'].splitlines()[0]}")
    for r in rows:
        if r["status"] == "FAILED":
            print("\n" + r["detail"])
    total = round(sum(r["seconds"] for r in rows), 1)
    print(f"{'total':20s} {'':7s} {total:>8.1f}")
    if failed:
        print(f"\nRELEASE GATE FAILED at step '{failed}'. Do not run the holdout.")
        return 1
    meta = json.loads(SEED_META.read_text(encoding="utf-8"))
    meta["release_gate"] = {"started": started, "passed": True, "total_seconds": total,
                            "steps": [{k: r[k] for k in ("step", "status", "seconds", "detail")} for r in rows]}
    SEED_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print("\nRELEASE GATE PASSED (runtimes recorded in data/demo/seed_meta.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
