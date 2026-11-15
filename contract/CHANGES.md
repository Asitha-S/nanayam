# Contract change requests

Format: date, who, endpoint/field, what and why. Asitha decides and updates API_CONTRACT.md.

| date | who | item | request | decision |
|---|---|---|---|---|
| 2026-11-13 | Asitha (review) | v1.0 → v1.1 | Applied external engineering review: config confidence null, question binding, correction table, refund/reversal exclusivity, recorded vs live voice, template-only money speech, as_of + scope notes, demo tools gated, VITE_API_BASE, eval conditions A–E + leakage test | Accepted |
| 2026-11-13 | Asitha (review 2) | v1.1 clarifications | Confidence format rule (4 dp string in DB/hash, number in API); precision split by source on Learning screen; release gate + seed_meta.json; fixture-mode rule for 14:00 | Accepted, no contract shape change |
| 2026-11-13 | Asitha (review 3) | docs only | Release gate cleanup made an exact command (generated files only); Learning screen data sources stated (/learning vs /evaluation) | Accepted |
| 2026-11-14 | Asitha | POST `/payments` example | `reasons` example had 5 items but the rule is max 4. Example now has 4, matching the fixture | Accepted |
| 2026-11-14 | Asitha | GET `/payments/{txn}` example | `initial_prediction.classification_source` and the first history entry's `source` are `RULE` for Lakshmi's first payment (rule 5c), matching POST `/payments` and the fixture | Accepted |
| 2026-11-14 | Asitha | GET `/merchants/{id}/payments` | Clarified: `confidence` = initial prediction's confidence (null for `MERCHANT_CONFIG`); `classification_source` = current source. Sentence added to the contract | Accepted |
| 2026-11-14 | Asitha | clock (no shape change) | now = DEMO_DATE + real IST time of day. Ledger `created_at` = max(now, event time, previous entry's created_at for that merchant), so it never goes backwards in a chain. Expense "not in the future" uses the same effective now. Only `backend/app/clock.py` reads the system clock | Accepted |
| 2026-11-14 | Asitha | threshold (no shape change) | Effective threshold = max(model artifact threshold, `CONF_THRESHOLD`). `/health` reports the effective value | Accepted |
| 2026-11-14 | Asitha | seed history (no shape change) | M001 history gets exactly 3 fixed payments left unanswered: Mani ₹3,000 (2026-10-29), Jaya ₹1,000 (2026-10-30), Prabhu ₹1,500 (2026-10-31), each 20:05, P2P, PERSONAL, payers with no other history. They go through the normal classifier and must come out ASK; the simulated merchant skips only these. Test asserts exactly 3 OPEN questions in M001's seed, all dated 29-31 Oct | Accepted |
| 2026-11-14 | Asitha | `/evaluation` `questions_per_day_by_week` | Test period is 30 days: weeks are days 1-7, 8-14, 15-21 and "Days 22-30" (labelled that way in latest.json) | Accepted |
| 2026-11-14 | Asitha | `demo_key` values | `demo_key` = path under `assets/demo_audio/` without extension, including the language folder (`ta/expense_koyambedu`, `te/answer_family`), because ta/ and te/ share file names. `python -m backend.app.sarvam.register_demo_clips` writes `cache/sarvam_demo/demo_clips.json` | Accepted 2026-11-14; VOICE_AND_NOTICE §10 updated |
