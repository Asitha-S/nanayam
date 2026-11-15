"""python -m scripts.smoke   (from the repository root, after the release gate)

Starts the real backend (uvicorn) on a free port with a throwaway database, restores the committed seed via
/demo/reset, drives the M001 demo journey over HTTP and checks every number (DATA_AND_LOGIC 3.3). Prints a
pass/fail table and exits non-zero on any failure. The server is always stopped at the end.
Then a second server with UDHARI=true runs the credit-book journey (contract section 13).
The server runs with DEMO_TIME=21:30, so every scripted demo-day event is in the past at any real time of day.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
DEMO_TIME = "21:30"
SCRIPT = json.loads((REPO / "data" / "demo" / "M001_demo_day.json").read_text(encoding="utf-8"))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Smoke:
    def __init__(self, http):
        """http: any httpx-compatible client whose base URL ends in /api (a live server or a TestClient)."""
        self.http = http
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
        va = self.http.post("/voice/answer", json={"merchant_id": "M001", "language": "ta", "intent": "ASK_DAILY_PROFIT",
                                                   "date": "2026-11-15"}).json()
        spoken = all(n in va.get("text", "") for n in ("4,820", "3,100", "1,720", "2,000"))
        self.check("voice answer (template + slot check)", spoken and va["number_check"]["passed"]
                   and va["facts"]["profit"]["amount_paise"] == 172000, va.get("text", "")[:40] + "...")
        csv_text = self.http.get("/merchants/M001/export/csv", params={"start_date": "2026-11-15", "end_date": "2026-11-15"}).text
        data = [l for l in csv_text.splitlines() if not l.startswith("#")][1:]
        paid = sum(round(float(l.split(",")[7]) * 100) for l in data if l.split(",")[2] == "PAYMENT_IN")
        self.check("CSV export", len(data) == 17 and paid == 682000 and "# ledger verify: VALID" in csv_text,
                   f"{len(data)} rows, PAYMENT_IN Rs {paid // 100}")
        pdf = self.http.get("/merchants/M001/export/pdf", params={"start_date": "2026-11-15", "end_date": "2026-11-15"}).content
        import io

        from pypdf import PdfReader

        pdf_text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        self.check("PDF CA pack (₹ embedded)", pdf.startswith(b"%PDF") and "₹1,720" in pdf_text
                   and "Recorded profit" in pdf_text, f"{len(pdf)} bytes")
        notice = json.loads((REPO / "data" / "demo" / "notice_numbers.json").read_text(encoding="utf-8"))
        image = REPO / "assets" / "notice" / "sample_notice.png"
        upload = image.read_bytes() if image.exists() else b"sample notice placeholder bytes"
        an = self.http.post("/notices/analyse", data={"merchant_id": "M001", "demo_key": "sample_notice_v1"},
                            files={"file": ("sample_notice.png", upload, "image/png")})
        a = an.json()
        self.check("notice analyse (sample)", an.status_code == 201 and a.get("from_cache") is True
                   and a["fields"]["amount_questioned_paise"]["value"] == notice["amount_questioned_paise"],
                   f"{a.get('notice_id')}, period {a['fields']['period_start']['value']}..{a['fields']['period_end']['value']}")
        nid = a["notice_id"]
        ev = self.http.get(f"/merchants/M001/notices/{nid}/evidence").json()
        self.check("notice evidence", ev.get("difference_vs_notice", {}).get("amount_paise") == 0
                   and ev["ledger_view"]["unresolved"]["entry_count"] == 3
                   and any(x["payer_name"] == "Karthik" for x in ev["family_transfer_examples"]),
                   f"{notice['amount_questioned_display']}, difference 0, unresolved 3")
        vi = self.http.post("/voice/interpret", json={"merchant_id": "M001", "language": "ta", "text": "இன்னைக்கு எவ்வளவு லாபம்",
                                                      "voice_log_id": None, "open_question_id": None}).json()
        ve = self.http.post("/voice/interpret", json={"merchant_id": "M001", "language": "ta",
                                                      "text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen",
                                                      "voice_log_id": None, "open_question_id": None}).json()
        lp = self.http.post("/demo/live-payment", json={"merchant_id": "M001"})
        lpj = lp.json()
        self.check("live payment (POST /payments path)", lp.status_code == 201 and lpj["transaction_id"].startswith("LIVE-M001-"),
                   f'{lpj.get("payer_name")} {lpj.get("amount_display")} {lpj.get("action")}')
        an = self.http.get(f"/payments/{lpj['transaction_id']}/announcement?language=ta").json()
        self.check("Soundbox announcement (template)", an["text"].endswith("வந்திருக்கு."), an["text"])
        now = self.http.get("/health").json()["now"]
        pay = {"merchant_id": "M001", "payer_id": "P10411", "payer_name": "Senthil K", "payer_vpa_kind": "PERSONAL",
               "amount_paise": 5000, "payment_type": "P2M", "timestamp": now, "description": None}
        hdr = {"X-Naanayam-Client": "pay-page"}
        p1 = self.http.post("/payments", json={**pay, "transaction_id": "PAY-SMOKE-1"}, headers=hdr)
        p2 = self.http.post("/payments", json={**pay, "transaction_id": "PAY-SMOKE-2"}, headers=hdr)
        self.check("/pay page: one payment per 2 s", p1.status_code == 201 and p2.status_code == 429,
                   f"{p1.status_code} then {p2.status_code}")
        self.check("voice interpret reads the text",
                   vi.get("intent") == "ASK_DAILY_PROFIT" and ve.get("intent") == "LOG_EXPENSE"
                   and ve["entities"]["amount_display"] == "₹3,100" and ve["entities"]["category"] == "STOCK_PURCHASE",
                   f'{ve.get("interpreter")}: {ve["entities"].get("amount_display")} {ve["entities"].get("category")}')
        off = self.http.get("/merchants/M001/tabs")
        self.check("udhari off by default", off.status_code == 404 and h.get("features") == {"udhari": False},
                   f"tabs HTTP {off.status_code}")

    def run_udhari(self) -> None:
        """UDHARI=true: seeded tabs, a customer paying part of the tab in live mode, voice credit, dues."""
        h = self.http.get("/health").json()
        self.check("udhari on", h.get("features") == {"udhari": True}, "UDHARI=true")
        self.http.post("/demo/reset", json={})
        t = self.http.get("/merchants/M001/tabs").json()
        self.check("udhari seed: 4 open tabs", (t["open_count"], t["total_due_display"]) == (4, "₹4,810"),
                   ", ".join(f'{i["payer_name"]} {i["due_display"]}' for i in t["items"]))
        lp = self.http.post("/demo/live-payment", json={"merchant_id": "M001"}).json()
        offer = self.http.get(f"/payments/{lp['transaction_id']}/announcement?language=ta").json().get("tab_offer") or {}
        self.check("udhari: live payment offers the tab", lp["payer_name"] == "Ramesh N" and lp["action"] == "AUTO_CLASSIFY"
                   and offer.get("due_display") == "₹2,300" and offer.get("settle_display") == "₹2,000",
                   f'{lp["payer_name"]} {lp["amount_display"]} {lp.get("classification")}, due {offer.get("due_display")}')
        before = self.totals()
        st = self.http.post("/tabs/P10006/settle", json={"client_request_id": str(uuid.uuid4()), "merchant_id": "M001",
                                                         "transaction_id": lp["transaction_id"]})
        stj = st.json()
        self.check("udhari: settle takes it off", st.status_code == 201 and stj["amount_display"] == "₹2,000"
                   and stj["due_display"] == "₹300", f'{stj.get("amount_display")} off, {stj.get("due_display")} due')
        self.check("udhari: ledger and summary untouched", self.totals() == before, "summary identical after settle")
        vi = self.http.post("/voice/interpret", json={"merchant_id": "M001", "language": "ta", "text": "ரமேஷ் 300 கடன்"}).json()
        e = vi.get("entities") or {}
        ad = self.http.post(f"/tabs/{e.get('payer_id')}/add", json={
            "client_request_id": str(uuid.uuid4()), "merchant_id": "M001", "amount_paise": e.get("amount_paise"),
            "input_source": "VOICE", "language": "ta", "utterance_text": "ரமேஷ் 300 கடன்"})
        self.check("udhari: voice credit (ADD_CREDIT)", vi.get("intent") == "ADD_CREDIT" and e.get("payer_name") == "Ramesh N"
                   and ad.status_code == 201 and ad.json()["due_display"] == "₹600",
                   f'{e.get("payer_name")} {e.get("amount_display")} -> due {ad.json().get("due_display")}')
        vd = self.http.post("/voice/interpret", json={"merchant_id": "M001", "language": "ta", "text": "யாரெல்லாம் பணம் தரணும்?"}).json()
        spoken = self.http.get("/merchants/M001/tabs?language=ta").json()["spoken"]["text"]
        self.check("udhari: who owes (ASK_DUES)", vd.get("intent") == "ASK_DUES" and spoken.startswith("4 பேர்"), spoken[:60])
        v = self.http.get("/merchants/M001/ledger/verify").json()
        self.check("udhari: ledger verify", v["status"] == "VALID", v["status"])


def serve(smoke: Smoke | None, step: str, **extra_env) -> Smoke | None:
    """Start a backend on a fresh database, run Smoke.<step> against it, stop it. None if it never started."""
    port = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="naanayam_smoke_"))
    env = {**os.environ, "DB_PATH": str(tmp / "smoke.db"), "ENABLE_DEMO_TOOLS": "true", "DEMO_MODE": "cache_only",
           "LOGS_DIR": str(tmp / "logs"), "DEMO_TIME": DEMO_TIME, "PYTHONIOENCODING": "utf-8", "UDHARI": "false",
           **extra_env}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                              cwd=REPO / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    http = httpx.Client(base_url=f"http://127.0.0.1:{port}/api", timeout=30)
    if smoke is None:
        smoke = Smoke(http)
    smoke.http = http
    try:
        for _ in range(120):
            try:
                if http.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            print("server did not start")
            return None
        try:
            getattr(smoke, step)()
        except Exception as exc:  # report the step that crashed instead of a traceback only
            smoke.check(f"unexpected error ({step})", False, f"{type(exc).__name__}: {exc}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return smoke


def main() -> int:
    started = time.monotonic()
    smoke = serve(None, "run")
    if smoke is None or serve(smoke, "run_udhari", UDHARI="true") is None:
        return 1
    print(f"\n{'check':32s} {'result':6s}  detail")
    for name, ok, detail in smoke.rows:
        print(f"{name:32s} {'pass' if ok else 'FAIL':6s}  {detail}")
    failed = [r for r in smoke.rows if not r[1]]
    print(f"\nSMOKE {'FAILED' if failed else 'PASSED'}: {len(smoke.rows) - len(failed)} of {len(smoke.rows)} checks "
          f"in {time.monotonic() - started:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
