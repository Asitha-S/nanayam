"""python -m scripts.smoke   (from the repository root, after the release gate)

Starts the real backend (uvicorn) on a free port with a throwaway database, restores the committed seed via
/demo/reset, drives the M001 demo journey over HTTP and checks every number (DATA_AND_LOGIC 3.3). Prints a
pass/fail table and exits non-zero on any failure. The server is always stopped at the end.
Needs the IST wall-clock time to be after 05:40 (the scripted expense time); otherwise the expense is "in the future".
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
SCRIPT = json.loads((REPO / "data" / "demo" / "M001_demo_day.json").read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Smoke:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base, timeout=30)
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        return ok

    def totals(self) -> tuple:
        s = self.http.get("/merchants/M001/summary").json()
        return (s["total_collections"]["amount_paise"], s["business_sales"]["amount_paise"],
                s["family_transfers"]["amount_paise"], s["pending"]["amount_paise"], s["expenses"]["amount_paise"],
                s["profit"]["amount_paise"], s["reconciliation_ok"])

    def run(self) -> None:
        h = self.http.get("/health").json()
        current = json.loads((REPO / "ml" / "artifacts" / "current.json").read_text(encoding="utf-8"))
        self.check("health", h["status"] == "ok" and h["db"] == "ok" and h["model_version"] == current["model_version"]
                   and h["tampered"] is False, f"model {h['model_version']}, threshold {h['threshold']}")
        r = self.http.post("/demo/reset", json={}).json()
        self.check("demo reset", r["pending_demo_payments"] == {"M001": 15, "M002": 11}, str(r["pending_demo_payments"]))
        e = self.http.post("/expenses", json=SCRIPT["expense"])
        self.check("expense ₹3,100 (05:40)", e.status_code == 201, f"HTTP {e.status_code}")
        self.check("row 1: morning totals", self.totals() == (0, 0, 0, 0, 310000, -310000, True), str(self.totals()))
        pays = [self.http.post("/demo/next-payment", json={"merchant_id": "M001"}).json() for _ in range(15)]
        autos = [p["action"] == "AUTO_CLASSIFY" and p["classification"] == "SALE" for p in pays[:14]]
        self.check("payments 1-14 AUTO SALE", all(autos), f"{sum(autos)} of 14")
        ask = pays[14]
        self.check("payment 15 asked (Lakshmi)", ask["action"] == "ASK_MERCHANT" and ask["suggested_classification"]
                   == "FAMILY" and ask["question_id"] is not None, f"confidence {ask['confidence']}, {ask['reasons'][:1]}")
        self.check("row 3: before answer", self.totals() == (682000, 482000, 0, 200000, 310000, 172000, True),
                   str(self.totals()))
        c = self.http.post(f"/payments/{ask['transaction_id']}/confirm", json={
            "merchant_id": "M001", "question_id": ask["question_id"], "confirmed_category": "FAMILY",
            "channel": "VOICE", "utterance_text": SCRIPT["answer"]["utterance_text"], "remember_payer": True}).json()
        self.check("confirm FAMILY + remember", c.get("question_status") == "ANSWERED"
                   and c["payer_memory"]["family_payer_configured"] is True, f"moved_from {c.get('moved_from')}")
        self.check("row 4: after answer", self.totals() == (682000, 482000, 200000, 0, 310000, 172000, True),
                   str(self.totals()))
        p = self.http.post("/classify/preview", json={"merchant_id": "M001", "payer_id": "P90001", "amount_paise": 200000,
                                                      "payment_type": "P2P", "timestamp": "2026-11-15T20:30:00+05:30"}).json()
        self.check("preview: your instruction", p["classification_source"] == "MERCHANT_CONFIG" and p["confidence"] is None
                   and p["written"] is False, p["reasons"][0])
        src = self.http.get("/merchants/M001/summary", params={"include_sources": "true"}).json()["sources"]
        traced = sum(self.http.get(f"/ledger/{i}").json()["amount_paise"] for i in src["business_sales"])
        self.check("sales trace to ledger entries", traced == 482000 and len(src["business_sales"]) == 14, f"₹{traced // 100}")
        v = self.http.get("/merchants/M001/ledger/verify").json()
        self.check("ledger verify", v["status"] == "VALID", v["message"])
        lst = self.http.get("/merchants/M001/payments").json()
        self.check("payments list", lst["count"] == 15, f"count {lst['count']}")
        lr = self.http.get("/merchants/M001/learning").json()
        kinds = {x["payer_name"]: x["kind"] for x in lr["payers"]}
        self.check("learning payers", kinds.get("Karthik") == "FAMILY_INSTRUCTION" and kinds.get("Selvi") == "MIXED"
                   and kinds.get("Lakshmi R") == "FAMILY_INSTRUCTION", f"Selvi {kinds.get('Selvi')}")
        ev = self.http.get("/evaluation").json()
        self.check("evaluation served", "headline" in ev and ev.get("data_label", "").startswith("Synthetic"),
                   f"{ev.get('run_id')} n_test_evaluations {ev.get('n_test_evaluations')}")
        tax = self.http.get("/merchants/M003/tax-summary").json()
        self.check("M003 GST UNKNOWN", tax["gst_treatment"] == "UNKNOWN", ", ".join(tax["flags"]))
        vi = self.http.post("/voice/interpret", json={"merchant_id": "M001", "language": "ta", "text": "இன்னைக்கு எவ்வளவு லாபம்",
                                                      "voice_log_id": None, "open_question_id": None})
        self.check("voice interpret (stub)", vi.status_code == 200, vi.json().get("intent", ""))


def main() -> int:
    port = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="naanayam_smoke_"))
    env = {**os.environ, "DB_PATH": str(tmp / "smoke.db"), "ENABLE_DEMO_TOOLS": "true", "DEMO_MODE": "cache_only",
           "LOGS_DIR": str(tmp / "logs"), "PYTHONIOENCODING": "utf-8"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                              cwd=REPO / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    smoke = Smoke(f"http://127.0.0.1:{port}/api")
    started = time.monotonic()
    try:
        for _ in range(120):
            try:
                if smoke.http.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            print("server did not start")
            return 1
        try:
            smoke.run()
        except Exception as exc:  # report the step that crashed instead of a traceback only
            smoke.check("unexpected error", False, f"{type(exc).__name__}: {exc}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    print(f"\n{'check':32s} {'result':6s}  detail")
    for name, ok, detail in smoke.rows:
        print(f"{name:32s} {'pass' if ok else 'FAIL':6s}  {detail}")
    failed = [r for r in smoke.rows if not r[1]]
    print(f"\nSMOKE {'FAILED' if failed else 'PASSED'}: {len(smoke.rows) - len(failed)} of {len(smoke.rows)} checks "
          f"in {time.monotonic() - started:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
