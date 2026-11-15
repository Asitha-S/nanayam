# Naanayam: Project Brief

> Read this file first. Then read the doc for your area. Do not change anything in `contract/` on your own.

| | |
|---|---|
| Product | **Naanayam** (நாணயம்: coin, and honesty). Formerly MunimAI. |
| Event | Paytm Build for India AI Hackathon, Chennai, 15 Nov 2026 |
| Track | Track 1: Merchant Growth AI |
| Team | Aether: Asitha Srithar, M Charulatha, Gummadi Nagasai Sree |
| Stack | Python 3.11, FastAPI, SQLite, scikit-learn / LightGBM, React (Vite), Sarvam AI APIs |

## 1. What we are building

**Naanayam: from payment collections to financial proof.**

Paytm's Soundbox tells merchants what came in. Naanayam helps them understand what they earned, explain what they received, and show what their business is worth.

Naanayam turns a small merchant's incoming UPI payments and voice-logged expenses into a **structured, traceable ledger**:

1. Every incoming payment is classified as **SALE** (business) or **FAMILY** (personal, not business: family, friends, loan repayments to the owner).
2. Confident classifications happen silently. Uncertain ones become a **question** to the merchant, asked by voice in Tamil or Telugu.
3. The merchant's answers are stored and used for that merchant's future payments (**feedback layer**).
4. The merchant logs expenses by voice ("Koyambedu-la 3,100 rupees-ku kaaikari vaanginen").
5. The backend calculates profit. The LLM only phrases numbers the backend has already calculated.
6. The same ledger produces three outputs ("three proofs"):
   - **Proof of profit** for the merchant (daily profit by voice).
   - **Proof for the taxman**: notice mode turns one sample GST notice into an evidence summary from the ledger, for a CA.
   - **Proof for the lender**: a sample "credit passport" showing recorded business income vs raw collections.

**Voice is the interface. The intelligent ledger is the product.** Never describe Naanayam as a chatbot, copilot or assistant.

## 2. What we are NOT building

- No real Paytm, bank, NPCI or GST portal integration. All payments are synthetic.
- No tax filing, no legal advice, no automatic notice replies.
- No loan decisions or credit scores.
- No GST treatment inferred from payment amounts. Ever.
- No per-transaction model retraining. Learning = the feedback layer described in `docs/DATA_AND_LOGIC.md`.

## 3. Scope priorities (never sacrifice a higher priority for a lower one)

| Priority | Feature | Owner |
|---|---|---|
| **P1 must work** | Synthetic payments and demo stream | Asitha |
| P1 | Classification with confidence, AUTO vs ASK | Asitha |
| P1 | Merchant confirmation (tap and voice) | Asitha (API), Nagasai Sree (UI), Charulatha (Tamil voice) |
| P1 | Voice expense logging in Tamil | Charulatha |
| P1 | Daily profit calculated by backend, answered in Tamil | Asitha (numbers; answer composer + slot check + TTS call since 2026-11-14), Charulatha (Tamil templates, voice) |
| P1 | Ledger view where every number links to its source entries | Asitha (API), Nagasai Sree (UI) |
| **P2 must demonstrate** | Feedback layer + held-out evaluation (precision AND coverage, before vs after) | Asitha |
| P2 | Evaluation / learning screen for judges | Nagasai Sree |
| **P3 strong additions** | Hash-chained audit trail + verify | Asitha |
| P3 | Notice mode (one predefined sample notice) | Charulatha (reading the notice: analyse(), Tamil explanation), Asitha (evidence endpoint, since 2026-11-14), Nagasai Sree (screen) |
| P3 | CA export (CSV, then PDF) | Asitha (since 2026-11-14, taken over from Charulatha with her agreement) |
| P3 | Telugu voice flow for the second merchant | Nagasai Sree |
| **P4 show only** | Credit passport screen | Asitha (API), Nagasai Sree (UI) |

## 4. Non-negotiable engineering rules

1. **The LLM never calculates money.** All amounts come from the backend finance layer.
2. **Every spoken or displayed rupee figure must match a backend value.** Voice answers are built from fixed templates with a positional slot check (see `docs/VOICE_AND_NOTICE.md` 6).
3. **Every ledger entry has a source** (`source_type` + `source_id`).
4. **Ledger is append-only.** Corrections are new entries. Nothing is updated or deleted in `ledger_entries`.
5. **Uncertain = ask, not guess.** Below the confidence threshold, a payment is `PENDING` until the merchant answers.
6. **Only merchant-confirmed labels feed the feedback layer.** The model's own auto-labels never train it.
7. **Idempotency everywhere.** Same `transaction_id` twice must never be counted twice. Expenses use `client_request_id`.
8. **Money is integer paise** in the database and API (`amount_paise`). Display strings are formatted by the backend (`amount_display`).
9. **Time is IST (Asia/Kolkata).** A "day" is an IST calendar day. Timestamps are ISO 8601 with `+05:30`.
10. **GST:** pure-category merchants get the category's treatment with a "CA to confirm" flag. Mixed merchants get `UNKNOWN`. Purchase mix is never presented as sales mix.
11. **Evaluation numbers come from an actual run** and are labelled "synthetic data". Never type a metric into the UI by hand.
12. **No agent changes endpoint names, field names or enums.** Propose changes in `contract/CHANGES.md` and tell Asitha.
13. **The demo must never depend on live internet.** Every scripted Sarvam call has a cached response (see DEMO_MODE).
14. **Recorded is never presented as live.** Scripted demo clips are labelled "Recorded demo clip" on screen. Live mic input is always transcribed from its own audio bytes.
15. **Money is spoken only through fixed templates.** The LLM interprets what the merchant says; it never phrases financial answers.
16. **Configured rules are not probabilities.** A payment decided by the merchant's own instruction (`MERCHANT_CONFIG`) has no model confidence (`confidence: null`). We say "Naanayam remembers the merchant's instruction", never "the model is 99% sure".
17. **"Profit" means recorded profit**: UPI business sales minus expenses the merchant entered. It excludes cash sales, unrecorded expenses and stock changes. Every profit screen, answer and export carries this scope note.
18. **The server revalidates everything.** Amounts, categories, merchant and question IDs are checked by the backend even if the frontend already checked them.

## 5. Repository layout and ownership

```
naanayam/
├── PROJECT.md                  (all; Asitha merges changes)
├── CLAUDE.md                   ("Read PROJECT.md and docs/ before working")
├── AGENTS.md                   (same pointer, for Antigravity)
├── contract/
│   ├── API_CONTRACT.md         (frozen; Asitha owns)
│   ├── CHANGES.md              (change requests)
│   └── fixtures/               (example JSON responses, one file per endpoint)
├── docs/
│   ├── DATA_AND_LOGIC.md
│   ├── VOICE_AND_NOTICE.md
│   └── BUILD_PLAN.md
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, db.py, schemas.py     (Asitha)
│   │   ├── routers/            (Asitha; voice + notice routers call Charulatha's modules)
│   │   ├── ledger/, finance/, classifier/, feedback/, demo/   (Asitha)
│   │   ├── export/             (Asitha since 2026-11-14: CSV + PDF, reads finance/ functions only)
│   │   ├── sarvam/             (client + cache: Asitha writes the client wrapper; Charulatha owns prompts/models used)
│   │   ├── voice/              (Charulatha: interpret, templates; answer.py: Asitha since 2026-11-14)
│   │   │   └── templates/ta.json (Charulatha), templates/te.json (Nagasai Sree)
│   │   └── notice/             (Charulatha: extraction (analyse), Tamil explanation; evidence.py, store.py: Asitha since 2026-11-14)
│   └── tests/                  (Asitha; Charulatha adds voice tests)
├── data/
│   ├── generator/              (Asitha)
│   ├── generated/              (gitignored except demo/)
│   ├── demo/                   (committed: demo-day fixtures, sample notice)
│   └── voice_tests/ta.jsonl, te.jsonl   (Charulatha, Nagasai Sree)
├── ml/                         (Asitha: train, calibrate, evaluate)
├── frontend/                   (Nagasai Sree)
├── assets/
│   ├── demo_audio/ta/, te/     (Charulatha, Nagasai Sree)
│   └── notice/sample_notice.png (Charulatha)
└── cache/
    ├── sarvam_dev/             (gitignored)
    └── sarvam_demo/            (COMMITTED: cached responses for every scripted demo call)
```

**Rule: only edit files in folders you own.** If you need a change elsewhere, ask the owner.

## 6. Environment variables (`.env`, never committed; `.env.example` is committed)

| Variable | Example | Meaning |
|---|---|---|
| `SARVAM_API_KEY` | (secret) | Each person uses their own key |
| `DEMO_MODE` | `cache_only` / `cache_first` / `live` | `cache_only`: never call Sarvam; `cache_first`: use cache, call on miss; `live`: always call |
| `DEMO_DATE` | `2026-11-15` | The backend's "today" (injectable clock) |
| `DB_PATH` | `backend/naanayam.db` | SQLite file |
| `CONF_THRESHOLD` | `0.90` | Minimum AUTO threshold (the training run may choose a higher one) |
| `ENABLE_DEMO_TOOLS` | `true` / `false` | Enables `/demo/*` endpoints (reset, next-payment, tamper). `false` → they return 404 |
| `VITE_API_BASE` | `http://localhost:8000/api` | Used by React (in `frontend/.env`; Vite only exposes `VITE_` variables). Set to `fixtures` to use `contract/fixtures/` |

## 7. How to run (target)

```
backend:   uvicorn app.main:app --reload --port 8000     (from backend/)
frontend:  npm run dev                                   (from frontend/, port 5173)
data:      python -m data.generator.run --seed 42
train:     python -m ml.train && python -m ml.evaluate
reset demo: POST /api/demo/reset
tests:     pytest backend/tests
```

## 8. Instructions for AI coding agents (Claude Code, Antigravity)

- Before writing code, read: this file, `contract/API_CONTRACT.md`, and the doc for your area.
- Implement only your owned folders. Match field names, enums and status codes **exactly**.
- If something in the contract is ambiguous, do not invent: write the question in `contract/CHANGES.md`.
- Frontend: use `contract/fixtures/` until the real backend is available; switch by changing `VITE_API_BASE` only.
- Prefer simple, readable code over clever code. This is a 1-day demo that must not break.
- Never compute money, confidence, or GST treatment in the frontend or the LLM.

## 9. Definition of done (ready for the noon mentor round)

1. A simulated payment enters the backend via `/api/payments` (or `/api/demo/next-payment`).
2. The classifier returns category, confidence and action.
3. An uncertain payment can be confirmed by tap and by Tamil voice.
4. The confirmation is stored and changes the next prediction for that payer.
5. An expense can be logged by Tamil voice and appears in the ledger.
6. Daily recorded profit is calculated by the backend and spoken in Tamil from a fixed template, matching the screen exactly, with the "UPI only, expenses you entered" note on screen.
7. Every number on the profit screen links to its ledger entries.
8. The evaluation screen shows real precision, coverage and before/after numbers from an actual run.
9. The whole demo runs with `DEMO_MODE=cache_only` and Wi-Fi turned off, with recorded clips labelled as recorded.
10. With Wi-Fi on and `DEMO_MODE=cache_first`, a judge can speak an unscripted Tamil sentence and it is transcribed live (or the app says plainly that it could not reach Sarvam).

**Principle: Naanayam must never claim more certainty than its records justify.**
