"""Warm the committed demo Sarvam cache, then prove the demo day runs offline.

    python scripts/warm_demo_cache.py             # warm (needs SARVAM_API_KEY in .env), then verify offline
    python scripts/warm_demo_cache.py --verify    # only the offline check

Warm: starts the backend on a throwaway database with DEMO_MODE=cache_first and SARVAM_CACHE_DIR=demo, and plays each
merchant's demo day (data/demo/{M}_demo_day.json: M001 Tamil, M002 Telugu) through the real API, so every scripted
Sarvam call is made once and written to cache/sarvam_demo/: the Soundbox's announcement of every scripted payment and
its question (/voice/speak), the question card's speech, every recorded demo clip
(assets/demo_audio/{ta,te}/*.wav: transcribe, then interpret), the day's spoken profit answer, and the sample notice.
Commit cache/sarvam_demo/ afterwards.
Verify: the same day with DEMO_MODE=cache_only (never calls Sarvam). Every speech/voice step must come from the cache.
Prints one line per step and exits 1 if anything the demo needs is missing.

Run register_demo_clips first after adding clips or the sample notice. Changing a model or voice in
backend/app/sarvam/models.py changes the cache keys: warm again afterwards.
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
DEMO = REPO / "data" / "demo"
CLIPS = REPO / "assets" / "demo_audio"
NOTICE = REPO / "assets" / "notice" / "sample_notice.png"
LANG = {"M001": "ta", "M002": "te"}
QUESTION_CLIPS = ("answer_", "remember_", "confirm_")  # clips spoken while a question card is open


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Run:
    def __init__(self, mode: str):
        self.mode, self.rows = mode, []

    def row(self, step: str, status: str, detail: str = "") -> None:
        self.rows.append((step, status, detail))
        print(f"  {status:5s} {step:44s} {detail}")

    def play_day(self, http: httpx.Client, merchant: str) -> None:
        lang = LANG[merchant]
        day = json.loads((DEMO / f"{merchant}_demo_day.json").read_text(encoding="utf-8"))
        print(f"\n{merchant} ({lang})")
        sent = [http.post("/demo/next-payment", json={"merchant_id": merchant}).json() for _ in day["payments"]]
        asked = sent[day["answer"]["demo_index"] - 1]
        # what the Soundbox says for every scripted payment (and the question), in the Sarvam voice
        spoken, total = 0, 0
        for p in sent:
            a = http.get(f"/payments/{p['transaction_id']}/announcement?language={lang}").json()
            for text in [a["text"]] + ([a["question"]["text"]] if a.get("question") else []):
                total += 1
                r = http.post("/voice/speak", json={"merchant_id": merchant, "language": lang, "text": text})
                spoken += r.status_code == 200
        self.row("speech: Soundbox announcements", "ok" if spoken == total else "FAIL", f"{spoken} of {total} in the Sarvam voice")
        qs = http.get(f"/merchants/{merchant}/questions?status=OPEN&date={day['demo_date']}").json()["items"]
        q = next((x for x in qs if x["transaction_id"] == asked.get("transaction_id")), None)
        if q is None:
            self.row("question card", "FAIL", "the scripted payment was not asked")
        else:
            ok = q["question_audio_id"] and http.get(f"/audio/{q['question_audio_id']}").status_code == 200
            self.row("speech: question card", "ok" if ok else "FAIL", q["question_audio_id"] or "no speech (cache miss)")

        clips = sorted((CLIPS / lang).glob("*.wav")) if (CLIPS / lang).exists() else []
        if not clips:
            self.row(f"recorded clips ({lang})", "WARN", f"none in assets/demo_audio/{lang}/ yet")
        for wav in clips:
            key = f"{lang}/{wav.stem}"
            r = http.post("/voice/transcribe", files={"audio": (wav.name, wav.read_bytes(), "audio/wav")},
                          data={"language": lang, "merchant_id": merchant, "demo_key": key})
            if r.status_code != 200:
                self.row(f"clip {key}: transcribe", "FAIL", f"{r.status_code} {r.text[:90]}")
                continue
            t = r.json()
            self.row(f"clip {key}: transcribe", "ok", f"{t.get('recognition_mode')} · {t.get('text', '')[:40]}")
            body = {"merchant_id": merchant, "language": lang, "text": t["text"], "voice_log_id": t.get("voice_log_id"),
                    "open_question_id": q["question_id"] if q and wav.stem.startswith(QUESTION_CLIPS) else None}
            r = http.post("/voice/interpret", json=body)
            self.row(f"clip {key}: interpret", "ok" if r.status_code == 200 else "FAIL",
                     r.json().get("intent", "") if r.status_code == 200 else f"{r.status_code} {r.text[:90]}")

        http.post("/expenses", json=day["expense"])
        if q is not None:
            a = day["answer"]
            http.post(f"/payments/{q['transaction_id']}/confirm",
                      json={"merchant_id": merchant, "question_id": q["question_id"], "confirmed_category": a["confirmed_category"],
                            "channel": a["channel"], "utterance_text": a["utterance_text"], "remember_payer": a["remember_payer"]})
        r = http.post("/voice/answer", json={"merchant_id": merchant, "language": lang, "intent": "ASK_DAILY_PROFIT",
                                             "date": day["demo_date"]})
        if r.status_code == 422 and lang == "te":
            self.row("speech: profit answer", "WARN", "no templates/te.json yet")
        elif r.status_code != 200:
            self.row("speech: profit answer", "FAIL", f"{r.status_code} {r.text[:90]}")
        else:
            ans = r.json()
            self.row("speech: profit answer", "ok" if ans.get("audio_id") else "FAIL",
                     ans.get("audio_id") or f"text only ({ans.get('audio_error')})")

        if merchant == "M001":
            if not NOTICE.exists():
                self.row("sample notice", "WARN", "assets/notice/sample_notice.png not committed yet")
            else:
                r = http.post("/notices/analyse", files={"file": (NOTICE.name, NOTICE.read_bytes(), "image/png")},
                              data={"merchant_id": merchant, "demo_key": "sample_notice_v1"})
                self.row("sample notice: analyse", "ok" if r.status_code == 200 else "FAIL",
                         "" if r.status_code == 200 else f"{r.status_code} {r.text[:90]}")


def run(mode: str) -> Run:
    """mode: 'cache_first' (warm, writes cache/sarvam_demo) or 'cache_only' (verify)."""
    tmp = Path(tempfile.mkdtemp(prefix="naanayam_warm_"))
    port = free_port()
    env = {**os.environ, "DB_PATH": str(tmp / "warm.db"), "LOGS_DIR": str(tmp / "logs"), "ENABLE_DEMO_TOOLS": "true",
           "DEMO_MODE": mode, "SARVAM_CACHE_DIR": "demo", "DEMO_TIME": "21:30", "PYTHONIOENCODING": "utf-8"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=REPO / "backend",
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = Run(mode)
    print(f"\n== {'WARM' if mode == 'cache_first' else 'VERIFY offline'} (DEMO_MODE={mode})")
    try:
        http = httpx.Client(base_url=f"http://127.0.0.1:{port}/api", timeout=120)
        for _ in range(120):
            try:
                if http.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise SystemExit("backend did not start")
        http.post("/demo/reset", json={})
        for merchant in LANG:
            if (DEMO / f"{merchant}_demo_day.json").exists():
                result.play_day(http, merchant)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return result


def main() -> int:
    if "--verify" not in sys.argv:
        from dotenv import dotenv_values
        if not (os.getenv("SARVAM_API_KEY") or dotenv_values(REPO / ".env").get("SARVAM_API_KEY")):
            print("SARVAM_API_KEY is not set (.env): warming needs it. Use --verify for the offline check only.")
            return 2
        run("cache_first")
    check = run("cache_only")
    fails = [r for r in check.rows if r[1] == "FAIL"]
    warns = [r for r in check.rows if r[1] == "WARN"]
    print(f"\nOFFLINE DEMO {'NOT READY' if fails else 'READY'}: {len(fails)} missing, {len(warns)} warnings")
    if "--verify" not in sys.argv and not fails:
        print("Commit cache/sarvam_demo/ now.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
