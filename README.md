# Naanayam (நாணயம்)

From payment collections to financial proof. Paytm Build for India AI Hackathon, Chennai, 15 Nov 2026 (Track 1: Merchant Growth AI). Team Aether.

**Start here:** read [PROJECT.md](PROJECT.md), then [contract/API_CONTRACT.md](contract/API_CONTRACT.md), then the doc for your area:

| Who | Read | Owns |
|---|---|---|
| Asitha | everything | backend core, data, ml, contract |
| M Charulatha | [docs/VOICE_AND_NOTICE.md](docs/VOICE_AND_NOTICE.md), [docs/DATA_AND_LOGIC.md](docs/DATA_AND_LOGIC.md) §7.3 §9 | `backend/app/voice/`, `backend/app/notice/`, `backend/app/export/`, `templates/ta.json`, `data/voice_tests/ta*` |
| Gummadi Nagasai Sree | [docs/VOICE_AND_NOTICE.md](docs/VOICE_AND_NOTICE.md) §4 §7 §8 §11.5 | `frontend/`, `templates/te.json`, `data/voice_tests/te*` |
Plan and checkpoints: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md). Contract change requests: [contract/CHANGES.md](contract/CHANGES.md). Example responses for every endpoint: [contract/fixtures/](contract/fixtures/).

## Status

**Real (SQLite):** `POST /payments`, `GET /payments/{txn}`, payments list, expenses list, questions, confirm (question binding + correction table), `POST /expenses`, refund, reversal, expense void, `/classify/preview`, `/evaluation`, merchants (GET/PUT), `/learning`, `/tax-summary`, `/passport`, `/demo/tamper`, `/summary` with sources, `/ledger`, `/ledger/{id}`, `/ledger/verify`, `/demo/reset`, `/demo/next-payment`, `/demo/script`, `/health`. Also real: the error shape, request validation, the Sarvam client with its content-hash cache and demo-clip check, `money.display`, the clock, ledger hashing/verification, and the data generator.

**Classifier:** trained LightGBM + out-of-fold isotonic calibration (`ml/artifacts/`, `python -m ml.train`), with the DATA §5.6 decision procedure: q_model first, then your instructions (family / customer lists, each with a guardrail), payer memory (k chosen on the calibration set) and rules 5a–5c. `/health` shows the model version. Baseline: tag `model-freeze-1`.

**Real since 2026-11-14 (Asitha):** `/voice/answer` (templates + slot check + TTS), `/export/csv`, `/export/pdf`, notice evidence.

**Still fixture stubs**, owned by Charulatha: `/voice/transcribe`, `/voice/interpret`, `/voice/speak`. `/notices/analyse` is an agreed fallback until her reader lands: the committed sample (`demo_key=sample_notice_v1`) is stored and returned, anything else is 503.

`GET /evaluation` serves `data/eval/latest.json` from the final holdout run (conditions A–E, never hand-edited). Robustness results: `data/eval/robustness.json`. Every evaluation execution is logged in `data/eval/experiment_log.jsonl`.

`/demo/reset` restores the committed `data/demo/seed.db`. Integration guide for the team: [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Setup

Python 3.11 or newer.

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"           # add ,ml for the generator and training: ".[dev,ml]"
copy .env.example .env            # macOS/Linux: cp .env.example .env ; then put your SARVAM_API_KEY in .env
```

## Run

From the repository root (the venv active):

```
1. release gate     python -m scripts.release_gate       generator (seed 42) -> train -> seed.db -> checks -> all tests;
                                                         stops at the first failure, exits non-zero, prints per-step times
2. backend          cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000   -> http://localhost:8000/api/health
   API docs         http://localhost:8000/docs
   frontend         cd frontend && npm install && npm run dev            -> http://localhost:5173 (listens on all interfaces)
3. smoke test       python -m scripts.smoke              own server + throwaway DB; the M001 demo over HTTP
4. tests only       pytest                               (300 s per-test timeout; 900 s for seed/evaluation tests)
5. robustness       python -m scripts.robustness         other generator seeds only, never the holdout (~25 min)
6. final holdout    python -m ml.evaluate --holdout      ONLY when the team agrees; logged and counted
```

After the gate, commit `data/demo/seed.db`, `seed_meta.json`, `notice_numbers.json` and `ml/artifacts/` together.

**Udhari (credit book), off by default:** start the backend with `UDHARI=true` (or put it in `.env`) to turn on the tab book: an Udhari screen, "ரமேஷ் 300 கடன்" on Talk, and a "take it off the tab?" card on the Soundbox. After a demo reset four of Murugan's regulars have open tabs (₹4,810 in all) and Ramesh N pays ₹2,000 on the first live payment. It never touches the ledger, a payment's classification or the profit figures. Off, nothing changes.

**Demo laptop, the clock:** leave `DEMO_TIME` empty. The backend's day is `DEMO_DATE` (2026-11-15) at the real time of day, so live payments (Soundbox live mode, phones on /pay) carry the time they really arrived. The scripted day (judge tour, demo panel) still works at any hour: its payments keep their scripted times and nothing is rejected as "in the future"; the tour logs the morning expense through Talk at the current time. Only the smoke test pins `DEMO_TIME=21:30` (it posts the scripted 05:40 expense), and the cache warm-up does the same.

**Demo laptop, phones paying on /pay:**
1. Put the laptop and the phones on the same Wi-Fi or the laptop's hotspot. Start the backend with `--host 0.0.0.0` and the frontend with `npm run dev` (it already listens on all interfaces).
2. Windows asks once whether Python and Node may accept connections: tick **Private networks** and allow both. If the prompt was dismissed: Windows Security → Firewall & network protection → Allow an app through firewall → allow `python.exe` (the venv's) and `node.exe` on Private. The hotspot or Wi-Fi must be set to a Private network.
3. The Soundbox screen shows a QR code and the address under it (`http://<laptop LAN IP>:5173/#/pay`). A phone that scans it pays through the laptop's API at the same address on port 8000; nothing points at "localhost".
4. The /pay page says "Simulated payment. No real money moves." It accepts ₹1 to ₹50,000 and one payment every 2 seconds per phone.

Frozen: tag `model-freeze-2` (model `clf-20261114-e8dfc2`, τ 0.99, k 0.5). No changes to generator, features, model, calibration, threshold, k or rules after it.

The frontend can work without the backend: set `VITE_API_BASE=fixtures` in `frontend/.env` to read `contract/fixtures/` directly.

Using Sarvam: always go through `backend/app/sarvam/client.py` (`stt`, `chat`, `tts`, `vision`). Develop with `DEMO_MODE=cache_first` so repeated runs cost no credits. Model IDs live only in `backend/app/sarvam/models.py`. After recording demo clips into `assets/demo_audio/{ta,te}/`, run `python -m backend.app.sarvam.register_demo_clips` from the repo root.

## Contributing

- Branches: `asitha/*`, `charu/*`, `naga/*`. Small PRs into `main`; Asitha merges. `main` must always run.
- Only edit the folders you own. Never rename endpoints, fields or enums: write a request in `contract/CHANGES.md`.
- Never commit `.env` or API keys.
- **No AI co-author lines in commits or PRs.** Do not add `Co-Authored-By: Claude` (or any AI) trailers or "Generated with ..." lines. If you use an AI coding agent, tell it so; `CLAUDE.md` and `AGENTS.md` already say this.
