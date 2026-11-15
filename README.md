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

**Real (SQLite):** `POST /payments`, `GET /payments/{txn}`, payments list, expenses list, questions, confirm (question binding + correction table), `POST /expenses`, refund, reversal, expense void, `/classify/preview`, `/evaluation`, `/summary` with sources, `/ledger`, `/ledger/{id}`, `/ledger/verify`, `/demo/reset`, `/demo/next-payment`, `/demo/script`, `/health`. Also real: the error shape, request validation, the Sarvam client with its content-hash cache and demo-clip check, `money.display`, the clock, ledger hashing/verification, and the data generator.

**Classifier:** trained LightGBM + isotonic calibration (`ml/artifacts/`, `python -m ml.train`), with the DATA §5.6 decision procedure, payer memory and rules 5a–5c. `/health` shows the model version.

**Still fixture stubs** (return `contract/fixtures/`, always M001-shaped): tamper, merchants, voice, learning, tax summary, notices, passport, export.

`GET /evaluation` serves `data/eval/latest.json` from `python -m ml.evaluate` (conditions A–E, never hand-edited).

`/demo/reset` restores the committed `data/demo/seed.db`. Release gate (DATA §3.6): `python -m data.generator.run --seed 42`, `python -m ml.train`, `python -m data.seed_demo`, `pytest backend/tests/test_demo_day.py`; commit `seed.db`, `seed_meta.json` and `ml/artifacts/` together.

## Setup

Python 3.11 or newer.

```
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"           # add ,ml for the generator and training: ".[dev,ml]"
copy .env.example .env            # macOS/Linux: cp .env.example .env ; then put your SARVAM_API_KEY in .env
```

## Run

```
backend:   cd backend && uvicorn app.main:app --reload --port 8000      -> http://localhost:8000/api/health
docs:      http://localhost:8000/docs
tests:     pytest                                                       (from the repo root)
```

The frontend can work without the backend: set `VITE_API_BASE=fixtures` in `frontend/.env` to read `contract/fixtures/` directly.

Using Sarvam: always go through `backend/app/sarvam/client.py` (`stt`, `chat`, `tts`, `vision`). Develop with `DEMO_MODE=cache_first` so repeated runs cost no credits. Model IDs live only in `backend/app/sarvam/models.py`. After recording demo clips into `assets/demo_audio/{ta,te}/`, run `python -m backend.app.sarvam.register_demo_clips` from the repo root.

## Contributing

- Branches: `asitha/*`, `charu/*`, `naga/*`. Small PRs into `main`; Asitha merges. `main` must always run.
- Only edit the folders you own. Never rename endpoints, fields or enums: write a request in `contract/CHANGES.md`.
- Never commit `.env` or API keys.
- **No AI co-author lines in commits or PRs.** Do not add `Co-Authored-By: Claude` (or any AI) trailers or "Generated with ..." lines. If you use an AI coding agent, tell it so; `CLAUDE.md` and `AGENTS.md` already say this.
