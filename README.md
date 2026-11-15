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

**Still fixture stubs**, owned by Charulatha: `/voice/transcribe`, `/voice/interpret`, `/voice/speak`, `/notices/analyse`.

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
2. backend          cd backend && uvicorn app.main:app --reload --port 8000   -> http://localhost:8000/api/health
   API docs         http://localhost:8000/docs
3. smoke test       python -m scripts.smoke              own server + throwaway DB; the M001 demo over HTTP
4. tests only       pytest                               (300 s per-test timeout; 900 s for seed/evaluation tests)
5. robustness       python -m scripts.robustness         other generator seeds only, never the holdout (~25 min)
6. final holdout    python -m ml.evaluate --holdout      ONLY when the team agrees; logged and counted
```

After the gate, commit `data/demo/seed.db`, `seed_meta.json`, `notice_numbers.json` and `ml/artifacts/` together.

**Demo laptop:** set `DEMO_TIME=21:30` in `.env`. The backend's clock is then 2026-11-15 21:30 at any real time of day, so the scripted 05:40 expense and all demo-day payments are in the past (otherwise a morning rehearsal rejects the expense as "in the future"). The smoke test always runs its server with `DEMO_TIME=21:30`. Leave it empty in development.

Frozen: tag `model-freeze-2` (model `clf-20261114-e8dfc2`, τ 0.99, k 0.5). No changes to generator, features, model, calibration, threshold, k or rules after it.

The frontend can work without the backend: set `VITE_API_BASE=fixtures` in `frontend/.env` to read `contract/fixtures/` directly.

Using Sarvam: always go through `backend/app/sarvam/client.py` (`stt`, `chat`, `tts`, `vision`). Develop with `DEMO_MODE=cache_first` so repeated runs cost no credits. Model IDs live only in `backend/app/sarvam/models.py`. After recording demo clips into `assets/demo_audio/{ta,te}/`, run `python -m backend.app.sarvam.register_demo_clips` from the repo root.

## Contributing

- Branches: `asitha/*`, `charu/*`, `naga/*`. Small PRs into `main`; Asitha merges. `main` must always run.
- Only edit the folders you own. Never rename endpoints, fields or enums: write a request in `contract/CHANGES.md`.
- Never commit `.env` or API keys.
- **No AI co-author lines in commits or PRs.** Do not add `Co-Authored-By: Claude` (or any AI) trailers or "Generated with ..." lines. If you use an AI coding agent, tell it so; `CLAUDE.md` and `AGENTS.md` already say this.
