# Naanayam: Integration Guide

> For Charulatha (voice, notice, export) and Nagasai Sree (frontend, Telugu). Owner: Asitha.
> Read with `PROJECT.md`, `contract/API_CONTRACT.md` and `contract/CHANGES.md` (every change since v1.1 is logged there).

## 1. Running the backend

```
pip install -e ".[dev,ml]"                    # once
python -m scripts.release_gate                # generator -> train -> seed -> checks -> all tests; stops on the first failure
cd backend && uvicorn app.main:app --port 8000
python -m scripts.smoke                       # starts its own server, runs the M001 demo over HTTP, checks every number
```

`POST /api/demo/reset` restores `data/demo/seed.db` (built by the gate). Never edit `seed.db`, `ml/artifacts/` or
`data/eval/latest.json` by hand; the final holdout (`python -m ml.evaluate --holdout`) runs only when the team agrees.

## 2. What is real and what is a stub

| Area | Status | Owner |
|---|---|---|
| Payments, questions, confirm (incl. remember family / customer), expenses, refund, reversal, void, preview | Real | Asitha |
| Summary with sources, ledger, ledger entry, verify, tamper, demo reset / next-payment / script | Real | Asitha |
| Merchants GET/PUT, learning, evaluation, tax summary, passport, health | Real | Asitha |
| `/voice/transcribe`, `/voice/interpret`, `/voice/answer`, `/voice/speak`, `/audio/{id}` | **Stub** (fixtures; demo-clip hash check is real) | Charulatha |
| `/notices/analyse`, `/notices/{id}/evidence` | **Stub** (fixtures) | Charulatha |
| `/export/csv`, `/export/pdf` | **Stub** (CSV from the ledger fixture, one-line PDF) | Charulatha |

## 3. Checklist for Charulatha

The routers are Asitha's. Implement the functions below in your folders with these signatures; Asitha wires each
router to your function as soon as it exists (tell him in the PR). Never compute money yourself: amounts come from
`app.finance.summary.compute`, display strings from `app.money.display`, "now" from `app.clock`.

- [ ] **Sarvam constants**: confirm every `TODO(Charulatha)` in `backend/app/sarvam/models.py` against docs.sarvam.ai
      (model IDs, paths, auth header, language codes, TTS speaker). Vision path is `None` until confirmed.
- [ ] **Demo clips**: record `assets/demo_audio/ta/*.wav` (VOICE_AND_NOTICE §10), then
      `python -m backend.app.sarvam.register_demo_clips`. Demo keys include the language: `ta/expense_koyambedu`.
- [ ] **Templates**: `backend/app/voice/templates/ta.json` with every key in VOICE_AND_NOTICE §7. The backend already
      reads `question_payment` from it for question cards (`app/questions_text.py`); until the file exists it uses the drafts.
- [ ] **`app/voice/interpret.py`**: `interpret(conn, *, merchant_id, language, text, voice_log_id, open_question_id) -> dict`
      returning exactly the `/voice/interpret` response (contract §6), with the deterministic validation of §5.2.
- [ ] **`app/voice/answer.py`**: `daily_profit(conn, *, merchant_id, language, date) -> dict` returning the `/voice/answer`
      response. Take `facts` from `app.finance.summary.compute(conn, merchant_id, date, date)` (fields `business_sales`,
      `expenses`, `profit`, `family_transfers`, `pending_count`); template only; positional slot check (§6.3); raise on failure.
- [ ] **TTS**: use `app.sarvam.client.tts(text, lang)`; it returns `audio_id` and stores the WAV for `GET /audio/{id}`.
- [ ] **`app/notice/`**: `analyse(conn, *, merchant_id, file_bytes, demo_key) -> dict` and
      `evidence(conn, *, merchant_id, notice_id) -> dict` (contract §9). Use `app.sarvam.client.vision` and `chat`; ledger
      figures from `compute(...)` over the notice period; verify status from `app.services.insights.verify_status(conn, merchant_id)`.
- [ ] **Sample notice image**: amount **₹8,42,162** (= M001 gross UPI receipts 2026-08-01..2026-10-31, in
      `data/demo/notice_numbers.json`; regenerate the image if that file ever changes). Expected evidence on the
      committed seed: difference vs notice 0, unresolved 3 (Mani, Jaya, Prabhu, 29–31 Oct).
- [ ] **`app/export/`**: `csv_export(conn, *, merchant_id, start, end) -> bytes` and `pdf_export(...) -> bytes` with the
      columns and sections of contract §11; scope and attribution notes as in `/summary`.
- [ ] **Voice tests**: `data/voice_tests/ta_dev.jsonl`, `ta.jsonl`; `eval_voice` results committed.
- [ ] **Demo cache**: warm `cache/sarvam_demo/` in `DEMO_MODE=live` with `SARVAM_CACHE_DIR=demo` and commit it, so the
      demo runs with Wi-Fi off (`cache_only`).
- [ ] Before each PR: `python -m scripts.release_gate` and `python -m scripts.smoke` pass; no AI co-author lines in commits.

## 4. Checklist for Nagasai Sree (frontend)

- [ ] Switch from `VITE_API_BASE=fixtures` to the real backend screen by screen; fixtures stay the contract (README in `contract/fixtures/`).
- [ ] Confidence: show ≥ 0.995 as ">99%", never "100%"; `null` (`confidence_kind: NONE`) as "Your instruction".
- [ ] Question cards carry their `question_id`; never open questions by list position (the seed has 3 older OPEN ones).
- [ ] After a **SALE** answer on a **P2P** payment, offer "Remember as customer" (`remember_payer: true` with `SALE`).
      After a FAMILY answer, offer "Always family". Show `moved_from` when a payer moves between the two lists, and
      `suggest_unconfigure` ("Stop treating {name} as always family?").
- [ ] Guardrail questions (source `RULE`) lead with their reason: "Looks like a shop sale from a family payer" /
      "Looks like family money from a customer".
- [ ] Learning screen: headline = `/evaluation` `headline` and `questions_per_day_by_week` (C vs E); then
      `/merchants/{id}/learning` `payers` by `kind` (FAMILY_INSTRUCTION, CUSTOMER_INSTRUCTION, MIXED, MEMORY) with
      `source`. Precision by source is secondary, always next to the always-SALE baseline. Never type a metric by hand.
- [ ] Every number on Today links to `/ledger/{id}` via `summary.sources`; show the scope note.
- [ ] Telugu: `templates/te.json`, `te.jsonl`, M002 flow (Srinivas, ₹1,500).
