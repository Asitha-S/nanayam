"""python -m data.seed_demo   (from the repository root, after data.generator.run and ml.train)

Replays the generated history of M001-M003 (2026-08-01 to 2026-11-14) through the REAL backend
services (classifier, questions, feedback, ledger) in time order, with a simulated merchant who
answers every question correctly (0% error, DATA_AND_LOGIC 3.6), except the 3 fixed payments of
29-31 Oct, which stay unanswered. Writes:

  data/demo/seed.db             the database /demo/reset restores
  data/demo/seed_meta.json      generator seed, model, threshold, git commit, label mix, counts, sha256
  data/demo/notice_numbers.json M001 gross UPI receipts 2026-08-01..2026-10-31 for the sample notice

Refuses to run while the placeholder classifier is active unless --allow-placeholder is given
(the placeholder must never ship; the release gate runs without the flag).
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))  # import the backend exactly as uvicorn and pytest do

from app import clock, db, errors, money, repo  # noqa: E402
from app.classifier import placeholder  # noqa: E402
from app.classifier.decide import active_model_version, threshold  # noqa: E402
from app.schemas import ConfirmIn, ExpenseIn, PaymentIn, RefundIn, ReversalIn  # noqa: E402
from app.services import expenses as expense_svc  # noqa: E402
from app.services import payments as payment_svc  # noqa: E402

GENERATED = REPO_ROOT / "data" / "generated"
DEMO_DIR = REPO_ROOT / "data" / "demo"
DEMO_MERCHANTS = ("M001", "M002", "M003")
ANSWER_DELAY = timedelta(seconds=30)  # reversals come >= 60 s after a payment, so answers land first
NOTICE_PERIOD = ("2026-08-01", "2026-10-31")

# event priority when timestamps are equal
P_EXPENSE, P_PAYMENT, P_ANSWER, P_REFUND, P_REVERSAL = range(5)


def _load() -> dict[str, pd.DataFrame]:
    names = ("merchants", "payments", "refunds", "reversals", "expenses", "labels", "family_config")
    missing = [n for n in names if not (GENERATED / f"{n}.parquet").exists()]
    if missing:
        sys.exit(f"Missing {missing} in {GENERATED}. Run: python -m data.generator.run --seed 42")
    return {n: pd.read_parquet(GENERATED / f"{n}.parquet") for n in names}


def _events(d: dict[str, pd.DataFrame]) -> list:
    pay = d["payments"][d["payments"].merchant_id.isin(DEMO_MERCHANTS)]
    demo_txns = set(pay.transaction_id)
    ev = []
    for r in pay.itertuples(index=False):
        ev.append((clock.parse(r.timestamp), P_PAYMENT, r.transaction_id, "payment", r._asdict()))
    for r in d["refunds"][d["refunds"].transaction_id.isin(demo_txns)].itertuples(index=False):
        ev.append((clock.parse(r.timestamp), P_REFUND, r.refund_id, "refund", r._asdict()))
    for r in d["reversals"][d["reversals"].transaction_id.isin(demo_txns)].itertuples(index=False):
        ev.append((clock.parse(r.timestamp), P_REVERSAL, r.transaction_id, "reversal", r._asdict()))
    for r in d["expenses"][d["expenses"].merchant_id.isin(DEMO_MERCHANTS)].itertuples(index=False):
        ev.append((clock.parse(r.timestamp), P_EXPENSE, r.client_request_id, "expense", r._asdict()))
    heapq.heapify(ev)
    return ev


def _none(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def build(out_path: Path) -> dict:
    d = _load()
    labels = d["labels"].set_index("transaction_id")
    if out_path.exists():
        out_path.unlink()
    db.init_db(out_path)
    conn = db.connect(out_path)
    conn.execute("PRAGMA synchronous = OFF")  # build speed; the file is finalised below
    stats = {"answered": 0, "left_unanswered": 0, "answer_skipped_reversed": 0}
    try:
        with db.write_tx(conn):
            for m in d["merchants"][d["merchants"].merchant_id.isin(DEMO_MERCHANTS)].to_dict("records"):
                repo.insert_merchant(conn, {k: m[k] for k in ("merchant_id", "display_name", "owner_name", "city",
                                                               "business_category", "preferred_language", "created_at")})
            payers = pd.read_parquet(GENERATED / "payers.parquet").set_index("payer_id")
            for f in d["family_config"].to_dict("records"):
                repo.ensure_payer(conn, f["payer_id"], payers.loc[f["payer_id"], "payer_name"],
                                  payers.loc[f["payer_id"], "payer_vpa_kind"])
                repo.add_family_payer(conn, f["merchant_id"], f["payer_id"], f["relation_label"], f["added_at"],
                                      f["added_via"])

        events = _events(d)
        while events:
            ts, _, _, kind, row = heapq.heappop(events)
            with clock.frozen_at(ts):
                if kind == "payment":
                    req = PaymentIn(**{k: _none(row[k]) for k in PaymentIn.model_fields})
                    _, res = payment_svc.create_payment(conn, req)
                    if res["question_id"] is not None:
                        if labels.loc[req.transaction_id, "payer_role"] == "fixed_unanswered":
                            stats["left_unanswered"] += 1
                        else:
                            answer = {"merchant_id": req.merchant_id, "transaction_id": req.transaction_id,
                                      "question_id": res["question_id"],
                                      "confirmed_category": labels.loc[req.transaction_id, "true_label"]}
                            heapq.heappush(events, (ts + ANSWER_DELAY, P_ANSWER, req.transaction_id, "answer", answer))
                elif kind == "answer":
                    try:
                        payment_svc.confirm(conn, row["transaction_id"], ConfirmIn(
                            merchant_id=row["merchant_id"], question_id=row["question_id"],
                            confirmed_category=row["confirmed_category"], channel="TAP"))
                        stats["answered"] += 1
                    except errors.ApiError as exc:
                        if exc.code != "INVALID_STATE":
                            raise
                        stats["answer_skipped_reversed"] += 1
                elif kind == "refund":
                    payment_svc.refund(conn, row["transaction_id"], RefundIn(
                        refund_id=row["refund_id"], amount_paise=int(row["amount_paise"]),
                        timestamp=row["timestamp"], reason=_none(row["reason"])))
                elif kind == "reversal":
                    payment_svc.reverse(conn, row["transaction_id"], ReversalIn(
                        timestamp=row["timestamp"], reason=_none(row["reason"])))
                elif kind == "expense":
                    expense_svc.create_expense(conn, ExpenseIn(**{k: _none(row[k]) for k in ExpenseIn.model_fields}))

        with db.write_tx(conn):
            for mid in ("M001", "M002"):
                conn.execute("INSERT INTO demo_state (merchant_id, next_demo_index) VALUES (?, 1)", (mid,))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode = DELETE")  # one self-contained file to commit
        conn.execute("VACUUM")
        stats["counts"] = _counts(conn)
        stats["notice"] = _notice_numbers(conn)
    finally:
        conn.close()
    return stats


def _counts(conn) -> dict:
    out = {}
    for mid in DEMO_MERCHANTS:
        q = lambda sql: conn.execute(sql, (mid,)).fetchone()[0]  # noqa: E731
        out[mid] = {
            "payments": q("SELECT COUNT(*) FROM payments WHERE merchant_id = ?"),
            "questions_open": q("SELECT COUNT(*) FROM questions WHERE merchant_id = ? AND status = 'OPEN'"),
            "questions_answered": q("SELECT COUNT(*) FROM questions WHERE merchant_id = ? AND status = 'ANSWERED'"),
            "feedback": q("SELECT COUNT(*) FROM feedback WHERE merchant_id = ?"),
            "refunds": q("SELECT COUNT(*) FROM refunds r JOIN payments p USING (transaction_id) WHERE p.merchant_id = ?"),
            "reversals": q("SELECT COUNT(*) FROM reversals r JOIN payments p USING (transaction_id) WHERE p.merchant_id = ?"),
            "expenses": q("SELECT COUNT(*) FROM expenses WHERE merchant_id = ?"),
            "ledger_entries": q("SELECT COUNT(*) FROM ledger_entries WHERE merchant_id = ?"),
        }
    return out


def _notice_numbers(conn) -> dict:
    gross = conn.execute(
        "SELECT COALESCE(SUM(amount_paise), 0) FROM ledger_entries WHERE merchant_id = 'M001'"
        " AND entry_type = 'PAYMENT_IN' AND substr(effective_at, 1, 10) BETWEEN ? AND ?", NOTICE_PERIOD,
    ).fetchone()[0]
    return {
        "merchant_id": "M001",
        "period_start": NOTICE_PERIOD[0],
        "period_end": NOTICE_PERIOD[1],
        "amount_questioned_paise": gross,
        "amount_questioned_display": money.display(gross),
        "definition": "M001 gross UPI receipts in the notice period: sum of all PAYMENT_IN amounts, "
                      "before refunds and reversals (DATA_AND_LOGIC 3.7).",
    }


def _git() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True,
                                    text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-placeholder", action="store_true",
                    help="build with the placeholder classifier (integration only; never for the demo)")
    args = ap.parse_args()
    version = active_model_version()
    is_placeholder = version == placeholder.MODEL_VERSION
    if is_placeholder and not args.allow_placeholder:
        sys.exit("The placeholder classifier is active (no ml/artifacts/current.json). Train the model first "
                 "(python -m ml.train), or pass --allow-placeholder for an integration-only seed.")

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DEMO_DIR / "seed.db.building"
    stats = build(tmp)
    seed = DEMO_DIR / "seed.db"
    tmp.replace(seed)
    commit, dirty = _git()
    mix = json.loads((GENERATED / "label_mix.json").read_text(encoding="utf-8"))
    meta = {
        "generator_seed": mix["seed"],
        "model_version": version,
        "placeholder_classifier": is_placeholder,
        "threshold": threshold(),
        "git_commit": commit,
        "git_dirty": dirty,
        "created_at": clock.iso(clock.real_now()),
        "demo_date": clock.today().isoformat(),
        "seed_db_sha256": hashlib.sha256(seed.read_bytes()).hexdigest(),
        "label_mix": {"count_share": mix["count_share"], "value_share": mix["value_share"]},
        "replay": {k: stats[k] for k in ("answered", "left_unanswered", "answer_skipped_reversed")},
        "counts": stats["counts"],
    }
    (DEMO_DIR / "seed_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    notice = stats["notice"] | {"seed_db_sha256": meta["seed_db_sha256"]}
    (DEMO_DIR / "notice_numbers.json").write_text(json.dumps(notice, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    print(f"Wrote {seed} ({seed.stat().st_size / 1e6:.1f} MB), model {version}"
          + ("  ** PLACEHOLDER CLASSIFIER: integration only, never for the demo **" if is_placeholder else ""))
    print(json.dumps({"replay": meta["replay"], "counts": meta["counts"]}, indent=2))
    print(f"Notice amount (M001 gross UPI receipts {NOTICE_PERIOD[0]}..{NOTICE_PERIOD[1]}): "
          f"{notice['amount_questioned_display']}")


if __name__ == "__main__":
    main()
