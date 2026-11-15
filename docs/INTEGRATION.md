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
| `/voice/answer` (templates + positional slot check + TTS), `/audio/{id}` | Real | Asitha (since 2026-11-14) |
| `/voice/transcribe`, `/voice/interpret`, `/voice/speak` | **Stub** (fixtures; demo-clip hash check is real) | Charulatha |
| `/notices/{id}/evidence` | Real (reads the stored notice) | Asitha (since 2026-11-14) |
| `/notices/analyse` | **Fallback** (agreed): `demo_key=sample_notice_v1` stores and returns the sample's known fields; anything else 503 | Charulatha (`notice/analyse.py`) |
| `/export/csv`, `/export/pdf` | Real | Asitha (since 2026-11-14) |

## 3. Checklist for Charulatha

The routers are Asitha's. Implement the functions below in your folders with these signatures; Asitha wires each
router to your function as soon as it exists (tell him in the PR). Never compute money yourself: amounts come from
`app.finance.summary.compute`, display strings from `app.money.display`, "now" from `app.clock`.

- [ ] **Sarvam constants**: confirm every `TODO(Charulatha)` in `backend/app/sarvam/models.py` against docs.sarvam.ai
      (model IDs, paths, auth header, language codes, TTS speaker). Vision path is `None` until confirmed.
- [ ] **Demo clips**: record `assets/demo_audio/ta/*.wav` (VOICE_AND_NOTICE §10), then
      `python -m backend.app.sarvam.register_demo_clips`. Demo keys include the language: `ta/expense_koyambedu`.
- [ ] **Templates**: replace the minimal `backend/app/voice/templates/ta.json` (Asitha added only the profit keys, as
      drafted in VOICE_AND_NOTICE §7, so `/voice/answer` works) with the full reviewed file. Keep the profit keys' slot
      names and order (`{sales}`, `{expenses}`, `{profit}` / `{loss}`, `{family}`, `{pending_count}`): the slot check
      in `voice/answer.py` fails loudly (500, no speech) if they change. `question_payment` is read for question cards.
- [ ] **`app/voice/interpret.py`**: `interpret(conn, *, merchant_id, language, text, voice_log_id, open_question_id) -> dict`
      returning exactly the `/voice/interpret` response (contract §6), with the deterministic validation of §5.2.
- [x] ~~`app/voice/answer.py`~~ (taken over by Asitha, done). If Bulbul reads "4,820 ரூபாய்" badly (§6.4), tell Asitha:
      the digits-to-words conversion goes into the TTS input only.
- [ ] **`app/notice/analyse.py`**: replace the body of the fallback `analyse(conn, *, merchant_id, file_bytes, demo_key)`
      (keep the signature: the router calls it unchanged) with the real reader: `app.sarvam.client.vision` and `chat`,
      the §11.3 validation and deterministic field confidence, returning the contract §9 analyse response.
      **Store the result** with `app.notice.store.save_notice(conn, merchant_id=..., file_sha256=..., fields=<the
      response's "fields" object>, explanation_text=...)`; it returns the `notice_id` to put in the response. Evidence
      (`app/notice/evidence.py`, Asitha) reads exactly that row. Tamil explanation: figures from the evidence object.
      Tests to keep green: `test_analyse_sample_then_evidence_end_to_end` and the smoke test's two notice checks.
- [ ] **Sample notice image**: commit `assets/notice/sample_notice.png`, then run
      `python -m backend.app.sarvam.register_demo_clips` so `demo_key=sample_notice_v1` accepts only that file (422
      for anything else; until the image exists any file is accepted with a warning). Your real `analyse()` should call
      `app.notice.sample.check_sample_file(file_bytes)` for that key. Amount **₹8,42,162** (= M001 gross UPI receipts 2026-08-01..2026-10-31, in
      `data/demo/notice_numbers.json`; regenerate the image if that file ever changes). Expected evidence on the
      committed seed: difference vs notice 0, unresolved 3 (Mani, Jaya, Prabhu, 29–31 Oct).
- [x] ~~`app/export/`~~ (taken over by Asitha, done).
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
