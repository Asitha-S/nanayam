# Naanayam: Build Plan, Demo and Checklists

> Today: Fri 13 Nov. Build: Fri night + Sat 14 Nov. Event: Sun 15 Nov, Chennai (finishing touches only, demo-ready by the 12:00 mentor round).
> Rule for every block: **P1 working end to end beats P3 half done.** Check the cut list (section 6) the moment a block runs late.

---

## 0. Before anything else (Asitha, tonight)
- [ ] Email/ask the organisers: (1) is code written before the event allowed, or only planning/design? (2) is it fine that we present as "Naanayam" when the selected deck said "MunimAI"? If pre-built code is not allowed, this plan still works: keep everything as specs, data and recordings tonight, and do the build blocks at the venue in the same order with the cut list applied hard.
- [ ] Everyone: Sarvam account active, API key works (one test call each), credits visible.

---

## 1. Who owns what

| | Asitha (Claude Code) | M Charulatha (Tamil, Antigravity) | Gummadi Nagasai Sree (Telugu, Antigravity) |
|---|---|---|---|
| Core | Repo, stubs, Sarvam client + cache, generator, classifier, evaluation, feedback, ledger + hash, finance functions, payment/question/confirm/expense/summary/ledger/demo routers, preview, learning, passport API (last), seed DB, merges | Tamil voice: parse_amount, interpret, template answers + slot check, ta templates, Tamil test set, demo clips (ta). Notice: extraction, Tamil explanation, **evidence endpoint**. **CSV + PDF export.** (Notice and export only call Asitha's `finance` functions.) | Frontend: all screens, text + mic input, cards with binding rules, Soundbox simulator, demo panel UI; Telugu templates, Telugu test set, demo clips (te) |
| Docs to read | all | PROJECT, CONTRACT §0 §6 §7 §9 §11, VOICE_AND_NOTICE, DATA §7.3 §9 | PROJECT, CONTRACT (all), VOICE_AND_NOTICE §4 §7 §8 §11.5 |
| Merges | Asitha merges to `main` | PRs from `charu/*` | PRs from `naga/*` |

**Unblocking rule:** nobody waits for a finished backend. Tonight Asitha pushes (a) every router as a stub returning the matching file from `contract/fixtures/`, (b) the Sarvam client with cache, and (c) `finance` function signatures returning fixture numbers. Charulatha and Nagasai Sree build against those. Real logic replaces stubs behind the same signatures.

**Protect the 14:00 milestone:** if a real endpoint isn't ready, that screen stays on fixture mode for the integration run. Never delay the integrated demo waiting for anything that isn't Priority 1 (model quality, evaluation, notice, export, Telugu, passport).

---

## 2. Friday 13 Nov (tonight)

| time | Asitha | Charulatha | Nagasai Sree |
|---|---|---|---|
| 20:00–20:30 | Repo (private), push spec + fixtures, `.gitignore`, `.env.example`, CLAUDE.md, AGENTS.md. Add collaborators. | Read docs. Sarvam key test. | Read docs. Sarvam key test. |
| 20:30–22:00 | FastAPI skeleton, schema, `money.display`, `/health`, **all routers as fixture stubs**, Sarvam client + content-hash cache + `demo_clips.json` check. | Confirm Sarvam model IDs/params; STT on 5 Tamil clips; pick TTS voice; test number reading. Notes in `docs/SARVAM_NOTES.md`. | Vite + React skeleton, routes for all screens, API client using `VITE_API_BASE` (`fixtures` mode reads `contract/fixtures/`). |
| 22:00–00:00 | Generator (DATA §4), seed 42, print label mix. Demo-day script JSON for M001/M002 (values from DATA §3). | Fix every Tamil string; `ta.json`; `parse_amount` + unit tests (pure Python, needs nothing else). | Fix Telugu strings; `te.json`; Questions + Today screens on fixtures. |
| 00:00–00:30 | First model fit (quality not important yet). | Record ta demo clips + 10 dev clips. | Record te demo clips. |

**Friday exit:** stubs running; frontend shows fixture data; Sarvam works for all three; strings reviewed; generator runs. **Contract v1.1 frozen.**

---

## 3. Saturday 14 Nov: checkpoints (text first, then voice)

Each checkpoint is a 20-minute merge + check by all three. If a checkpoint fails, everyone helps fix it before moving on.

| deadline | non-negotiable result | main owners |
|---|---|---|
| **10:00** | Real DB; `seed.db` built from generator + replay; `/demo/reset`; `POST /payments`, `POST /expenses`, `/summary` real (classification may be a placeholder). | Asitha |
| **12:00** | Classifier + calibration + τ + rules 5a–5c; questions; confirm (with `question_id` binding, correction table); summary with sources. DATA §3.3 rows 1–4 pass in tests. | Asitha |
| **14:00** | **Full frontend ↔ backend with text input**: Soundbox → 15 payments → question card → tap answer → typed "Koyambedu-la 3,100 kaaikari" → `/voice/interpret` → card → save → Today numbers → tap a number → ledger entries. | All |
| **16:00** | **Tamil speech** for expense, profit and the Lakshmi answer (recorded clips and live mic). Template answers + slot check. **Run the whole flow once in `cache_only` with Wi-Fi off right here**, then keep doing so at every later checkpoint. | Charulatha + Nagasai Sree; Asitha wires routers |
| **18:00** | Evaluation run (conditions A–E, leakage test) → `latest.json`; Learning screen (A vs C vs E, precision split by source + config errors, curve, preview); every Today number traceable; ledger verify. | Asitha + Nagasai Sree |
| **20:00** | Notice mode **only if** everything above is solid: extraction, badges, evidence, Tamil explanation. CSV export. | Charulatha + Nagasai Sree |
| **21:00** | Offline rehearsal (Wi-Fi off, `cache_only`), bug fixes, backup video recorded. | All |
| **23:00** | **Freeze.** | |

**Drop rules:** behind at 16:00 → notice mode is dropped for now. Behind at 18:00 → no new features at all; only fixes and rehearsal. Telugu flow, PDF export, tamper demo and passport happen only after 21:00 if the rehearsal is clean, otherwise at the venue Sunday morning or never.

**Parallel work that never blocks a checkpoint:**
- Charulatha between checkpoints: `interpret.py` (LLM + validation + fallback) from 08:00, Tamil test set recording, then notice extraction from 16:00, export.
- Nagasai Sree: Talk screen with text box first (by 14:00), mic second, Learning screen, demo panel, Notice screen, then Telugu.
- Asitha after 12:00: evaluation script, preview, learning endpoint, integration help. Passport API only after 21:00.

---

## 4. Sunday 15 Nov: event day

| time | what |
|---|---|
| Before leaving | Pull `main` on both demo laptops. `pytest` passes. `/demo/reset`. Charge everything. |
| Arrival | Set up on venue power. Test speaker volume for Tamil audio. Test projector resolution (frontend at 1920×1080 and 1366×768). Run the demo once with Wi-Fi off. |
| Morning | Only fixes from the issue list. Rehearse the 3-minute demo 3 times; time it. Practise Q&A (section 9). |
| 12:00 | Mentor round: show the Murugan journey + evaluation screen. Write down every mentor comment. |
| After mentors | Fix only what is cheap and safe. Update pitch lines. Do not add features. |
| Before final demo | `/demo/reset`, Wi-Fi off, `cache_only`, open tabs in order, video ready on the second laptop. |

---

## 5. Git and environment rules
- Branches: `asitha/*`, `charu/*`, `naga/*`. Small PRs. Asitha merges. `main` must always run.
- Never commit `.env` or keys. Commit `cache/sarvam_demo/`, `data/demo/`, `data/demo/seed.db`, `ml/artifacts/`, `data/eval/latest.json`.
- Each AI agent session starts with: "Read PROJECT.md, contract/API_CONTRACT.md and docs/<your doc>. Only edit <your folders>. Do not change names or enums."
- If an agent wants to change the contract: it writes to `contract/CHANGES.md`; the human tells Asitha.

---

## 6. Cut list (drop in this order when late, never touch P1)
1. Passport (P4) → mention only.
2. PDF export → CSV only.
3. Telugu flow → show `te.json` and the Telugu test result only.
4. Tamper demo → keep the verify button only.
5. Notice Tamil audio → text only.
6. Notice mode entirely (if behind at 16:00).
7. Learning curve chart → numbers table only.
Never cut: confirmation step, question binding, template answers with slot check, idempotency, eval from a real run, offline cache, "Recorded demo clip" labelling.

---

## 7. Demo script (3 minutes; Asitha speaks, Charulatha operates voice, Nagasai Sree operates screens)

| t | screen | action | line |
|---|---|---|---|
| 0:00 | Title | | "Paytm's Soundbox tells Murugan what came in. It can't tell him what he earned, or prove it when someone asks. Naanayam turns his payments into records that prove." |
| 0:15 | Talk | Play `expense_koyambedu` (badge: Recorded demo clip) → card → "சரி" | "5:40 AM, Koyambedu. This is a clip we recorded so the demo doesn't depend on Wi-Fi; you can try the mic after. Naanayam understands, shows the amount, and saves only after he says yes." |
| 0:40 | Soundbox | Next payment ×14 (fast-forward button) | "Fourteen customers. All classified silently, with confidence." |
| 1:00 | Question | Payment 15: Lakshmi ₹2,000 → Tamil question plays → `answer_family` → remember prompt → `remember_yes` | "His sister sends ₹2,000. That isn't income. When Naanayam isn't sure, it asks. It never removes money from his income without asking." |
| 1:30 | Learning | Preview: next Lakshmi payment → "Family, your instruction" | "He told Naanayam to remember, so next time it doesn't ask. He can change that any time. For everyone else, his answers gradually reduce the questions." |
| 1:40 | Talk | `ask_profit` → Tamil answer plays, numbers highlight | "Sales 4,820. Expenses 3,100. Recorded profit 1,720. The AI never touches the maths: the ledger calculates it and the answer is a fixed template. UPI only, and only the expenses he entered: we say that on screen." |
| 2:00 | Today → tap ₹4,820 | source entries | "Every number opens the payments behind it." |
| 2:10 | Evaluation | | "On synthetic data from merchants the model never saw: always guessing 'sale' looks W% accurate but finds zero family money. Our full system decides X% on its own at Y% precision, and questions per day fall from A to B as merchants answer." |
| 2:25 | Notice | sample notice → fields with badges → evidence | "If a notice ever comes, the same ledger shows his CA what was business and what was family." |
| 2:45 | Ledger verify | | "Every record is hash-chained. If anyone edits one, we can tell." |
| 2:55 | Close | | "Others built assistants that talk. We built records that prove." |

Put the real W, X, Y, A, B from `latest.json` into the script on Saturday night. Never round up.

5-minute version adds: tamper demo, Telugu M002 in 30 s, passport screen, mixed kirana GST = UNKNOWN.

---

## 8. Backup plan
- Wi-Fi dies: nothing changes (cache_only).
- Mic/speaker fails: demo audio buttons + on-screen text.
- Backend crash: restart command on a sticky note (`uvicorn ...`), then `/demo/reset` and fast-forward to the current step via the demo panel.
- Laptop fails: second laptop with the same commit; backup video.
- A number on screen looks wrong: say "let me show the source" and open the ledger; never improvise a number.

---

## 9. Judge Q&A (agree the answers as a team)

| question | answer |
|---|---|
| Isn't this just Paytm's existing Munim / a chatbot? | Those record what the merchant tells them. Naanayam starts from the payments themselves, separates business from family money, and produces records a CA or lender can trace to each payment. Voice is how he uses it, not what it is. |
| How accurate is it? | Precision X% on payments it decides on its own, at Y% coverage, on held-out synthetic merchants. Everything else it asks. We report both because accuracy alone hides the questions. |
| Synthetic data? | Yes, clearly labelled. Real UPI data needs a partner. The evaluation method (unseen merchants, later period, precision with coverage) is what we'd run on real data. |
| What if the model is wrong? | It only auto-decides above a threshold tuned for 95% precision, and we measured the full system's precision separately, including the "remember" shortcut. It never removes money from income for a payer the merchant hasn't confirmed. Every decision can be corrected; the correction is a new ledger entry. |
| Is 0.99 / "remember" a model probability? | No. It's the merchant's own instruction, shown as "your instruction", with its own error count in the evaluation. |
| Was that speech live? | The scripted clips are recorded and labelled. Try the mic: if Wi-Fi works it goes to Sarvam live; if not, the app says so. |
| Is that really profit? | Recorded profit: UPI sales minus the expenses he entered. No cash, no stock changes. It says so on the screen. |
| Does the hash chain prove the income is true? | No. It shows records weren't edited after they were written. Truth comes from the payments plus the merchant's confirmations. |
| GST? | We never infer GST from amounts. A pure vegetable seller gets "likely exempt, CA to confirm". A mixed shop gets "unknown". |
| Is this legal/tax advice? | No. It organises records and explains a notice in plain Tamil. A CA decides. |
| Privacy? | Data stays with the merchant's account; the passport is shared only with consent. Nothing personal is sent to the LLM except the merchant's own words and payer display names. |
| Why Sarvam? | Tamil and Telugu speech in, natural speech out, and reading Indian documents, which is exactly where our users are. |
| Business model? | Add-on to the Soundbox subscription; better data for merchant lending; CA referrals. (Same as the deck.) |
| What did you build before today? | Answer honestly per what the organisers allowed. |

---

## 10. Pre-event checklist (Saturday 23:00)
- [ ] Release gate passed from a fresh database (DATA §3.6); `seed.db`, `seed_meta.json`, model artifact committed together.
- [ ] `pytest` green; `eval_voice` results committed; `latest.json` from a real run.
- [ ] `cache_only` full rehearsal with Wi-Fi off passed twice.
- [ ] Live mic tested with someone outside the team (Wi-Fi on, `cache_first`).
- [ ] `ENABLE_DEMO_TOOLS=true` on the demo laptop; `/health` shows `tampered: false` before going on stage.
- [ ] Backup video on both laptops and a phone.
- [ ] Demo panel works; reset takes < 2 s.
- [ ] README run steps tested on a fresh clone.
- [ ] Deck updated: name Naanayam, numbers from the real eval, no "verified income", no 44AD claim.
- [ ] Chargers, HDMI/USB-C adapters, small speaker, phone hotspot, printed demo script, sticky note with restart commands.
- [ ] Each person knows their lines and their screen.

---

## 11. First prompts for the coding agents

**Asitha → Claude Code (first session):**
"Read PROJECT.md, contract/API_CONTRACT.md and docs/DATA_AND_LOGIC.md fully. First: FastAPI skeleton where every endpoint is a stub returning the matching file in contract/fixtures/, plus the Sarvam client with content-hash cache. Then db schema, money.display with tests, /health. Do not write voice/, notice/ or export/ internals. Use integer paise, IST, append-only ledger, exact enum strings."

**Charulatha → Antigravity:**
"Read PROJECT.md, contract/API_CONTRACT.md sections 0, 6 and 9, and docs/VOICE_AND_NOTICE.md. Only edit backend/app/voice/, backend/app/notice/, backend/app/export/, backend/app/voice/templates/ta.json, data/voice_tests/ta*.jsonl. Implement parse_amount with unit tests first, then interpret.py with deterministic validation, then answer.py (fixed templates + positional slot check, no LLM for money). Notice evidence and exports call only the functions in backend/app/finance/. Use the Sarvam client in backend/app/sarvam/client.py; never call Sarvam directly."

**Nagasai Sree → Antigravity:**
"Read PROJECT.md, contract/API_CONTRACT.md and docs/VOICE_AND_NOTICE.md sections 4, 7, 8 and 11.5. Only edit frontend/, backend/app/voice/templates/te.json and data/voice_tests/te*.jsonl. Build the React app against contract/fixtures/ first (VITE_API_BASE=fixtures). Never compute or format money in the frontend; show amount_display. Follow the card binding rules in VOICE_AND_NOTICE 4.1a. Open questions by question_id, never by list position. Show 'Your instruction' instead of a percentage when confidence is null. Show the 'Recorded demo clip' badge when recognition_mode is RECORDED_DEMO. All UI text comes from the templates' ui.* keys."
