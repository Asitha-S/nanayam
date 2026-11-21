# Naanayam: Data and Logic Spec

> Owner: Asitha. Covers the database, the fixed demo dataset, the generator, the classifier, the feedback layer, the ledger, the finance definitions, GST, notice evidence, the passport and the evaluation protocol.
> Everything here must match `contract/API_CONTRACT.md`. If they disagree, the contract wins and this file gets fixed.

---

## 1. Database (SQLite)

All money columns are `INTEGER` paise. All timestamps are `TEXT` ISO 8601 with `+05:30`. Foreign keys on (`PRAGMA foreign_keys=ON`). WAL mode.

### 1.1 Tables

**merchants**
| column | type | notes |
|---|---|---|
| merchant_id | TEXT PK | `M001` |
| display_name | TEXT | |
| owner_name | TEXT | |
| city | TEXT | |
| business_category | TEXT | enum `business_category` |
| preferred_language | TEXT | `ta`/`te`/`en` |
| created_at | TEXT | |

**payers**
| column | type | notes |
|---|---|---|
| payer_id | TEXT PK | `P10001` |
| payer_name | TEXT | display name as UPI shows it |
| payer_vpa_kind | TEXT | `PERSONAL`/`BUSINESS` |

Payers are global (one person can pay several merchants), but all memory is per merchant.

**merchant_customer_payers** (merchant configuration, "Remember as customer")
| merchant_id | payer_id | added_at | added_via (`SETUP`/`CONFIRMATION`) |
PK (merchant_id, payer_id). A payer is never in both this table and merchant_family_payers.

**merchant_family_payers** (merchant configuration)
| merchant_id | payer_id | relation_label | added_at | added_via (`SETUP`/`CONFIRMATION`) |
PK (merchant_id, payer_id).

**payments** (raw facts as received; never updated except `reversed` flag is NOT stored here, see reversals)
| column | type | notes |
|---|---|---|
| transaction_id | TEXT PK | idempotency key |
| merchant_id | TEXT FK | |
| payer_id | TEXT FK | |
| amount_paise | INTEGER | > 0 |
| payment_type | TEXT | `P2M`/`P2P` |
| timestamp | TEXT | payment time |
| description | TEXT NULL | |
| payload_hash | TEXT | sha256 of the canonical request body, for idempotency comparison |
| received_at | TEXT | backend time |

**predictions** (one row per payment, written once)
| transaction_id PK FK | model_version | threshold REAL | q_model REAL (calibrated p(FAMILY); computed for every payment, including MERCHANT_CONFIG decisions) | p_final REAL NULL | confidence REAL NULL | confidence_kind (`MODEL`/`NONE`) | suggested_classification | action | classification_source | reasons_json | created_at |

**questions**
| question_id PK | merchant_id | transaction_id UNIQUE | status (`OPEN`/`ANSWERED`) | created_at | answered_at NULL |
`status` is the one mutable column in the system besides `demo_state`. It is a workflow flag, not financial data.

**feedback** (append only)
| feedback_id PK | merchant_id | transaction_id | payer_id | confirmed_category | previous_classification | q_model | channel | utterance_text NULL | remember_payer INTEGER | created_at |

**refunds** (append only)
| refund_id PK | transaction_id FK | amount_paise | timestamp | reason | payload_hash |

**reversals** (append only)
| transaction_id PK FK | timestamp | reason |

**expenses** (append only)
| expense_id PK | client_request_id UNIQUE | merchant_id | amount_paise | category | description | timestamp | input_source | language NULL | utterance_text NULL | voice_log_id NULL | payload_hash | created_at |

**expense_voids** (append only)
| expense_id PK FK | reason | created_at |

**ledger_entries** (append only, see section 7)
| column | type |
|---|---|
| ledger_entry_id | TEXT PK |
| merchant_id | TEXT |
| seq | INTEGER (per merchant, starts at 1, no gaps) |
| entry_type | TEXT |
| source_type | TEXT (`PAYMENT`/`EXPENSE`/`REFUND`/`REVERSAL`) |
| source_id | TEXT |
| supersedes_entry_id | TEXT NULL |
| amount_paise | INTEGER (always positive; meaning comes from entry_type) |
| classification | TEXT NULL (payments only) |
| classification_source | TEXT NULL |
| confidence | TEXT NULL (4 dp string, e.g. `"0.7100"`, so hashing is stable). Converted to/from a JSON number only in the repository layer; the API never returns the string |
| expense_category | TEXT NULL |
| effective_at | TEXT (when the money event happened) |
| created_at | TEXT (when the entry was written) |
| prev_hash | TEXT |
| hash | TEXT |
UNIQUE (merchant_id, seq).

**voice_logs**
| voice_log_id PK | merchant_id | language | audio_sha256 | transcript | intent NULL | entities_json NULL | outcome (`SAVED`/`ANSWERED`/`CONFIRMED`/`CLARIFY`/`CANCELLED`/`FAILED`) | created_at |

**notices**
| notice_id PK | merchant_id | file_sha256 | fields_json | explanation_text | created_at |

**demo_state**
| merchant_id PK | next_demo_index INTEGER |

### 1.2 Enforcement
- Repository layer exposes only `insert` for append-only tables. No `UPDATE`/`DELETE` functions exist for them. A test greps the backend for `UPDATE ledger_entries` / `DELETE FROM ledger_entries` and fails if found (except `demo/tamper.py`, which is excluded and only reachable through `/demo/tamper`).
- `/demo/reset` copies `data/demo/seed.db` over `DB_PATH`. No row-by-row cleanup.

---

## 2. IDs and formats

| ID | Format | Generated by |
|---|---|---|
| transaction_id | `TXN-{merchant}-{yyyymmdd}-{nnn}` (generator) | client / generator |
| expense_id | `EXP-{merchant}-{000000}` | backend, per-merchant counter |
| ledger_entry_id | `LE-{merchant}-{seq:06d}` | backend |
| question_id | `Q-{merchant}-{000000}` | backend |
| feedback_id | `FB-{merchant}-{000000}` | backend |
| refund_id | `RF-{merchant}-{000000}` | client / generator |
| voice_log_id | `VL-{merchant}-{000000}` | backend |
| audio_id | `AUD-{first 16 hex of sha256(lang + voice_id + text)}` | backend |
| notice_id | `NTC-{merchant}-{000}` | backend |

Display format (backend only): `₹` + Indian grouping, no decimals when paise is a multiple of 100, else 2 decimals. `482000 → "₹4,820"`, `12000000 → "₹1,20,000"`, `4550 → "₹45.50"`. One function, `money.display(paise)`, with unit tests for 0, 99, 100, 99999, 100000, 1234567, 10000000.

---

## 3. Fixed demo dataset

Everything in this section is committed in `data/demo/` and is the shared fixture for backend tests, frontend mocks and voice tests. **Do not change these values without CHANGES.md.**

### 3.1 Demo merchants

| merchant_id | display_name | owner | category | language | role in demo |
|---|---|---|---|---|---|
| M001 | Murugan Kaaikari Kadai | Murugan | VEGETABLES | ta | Main journey (Tamil) |
| M002 | Venkatesh Pandla Dukanam | Venkatesh | FRUITS | te | Second journey (Telugu) |
| M003 | Ravi Stores | Ravi | MIXED_KIRANA | ta | Shows `UNKNOWN` GST treatment only |

Location for all: Chennai. `created_at` = `2026-08-01T05:00:00+05:30`.

### 3.2 Named payers

| payer_id | name | kind | relation | merchant | behaviour |
|---|---|---|---|---|---|
| P20001 | Anbu Mess | BUSINESS | customer (bulk buyer) | M001 | P2M, every 1–3 days since Aug, ₹600–₹1,500 |
| P90001 | Lakshmi R | PERSONAL | Murugan's sister (Akka) | M001 | **No history.** First ever payment on demo day |
| P90002 | Karthik | PERSONAL | Murugan's brother (Thambi) | M001 | Configured family payer at setup. Sends ₹1,000–₹3,000, roughly weekly, P2P |
| P90003 | Selvi | PERSONAL | Murugan's wife's cousin | M001 | Pays twice for goods (SALE) and three times family money in history: a **mixed payer** |
| P20011 | Hotel Sri Sai | BUSINESS | customer | M002 | P2M bulk buyer |
| P90011 | Srinivas | PERSONAL | Venkatesh's brother | M002 | No history. First payment on demo day |
| P10001–P19999 | Customer names from a fixed list | PERSONAL | customers | all | Generated |

### 3.3 M001 demo day: 2026-11-15 (script `data/demo/M001_demo_day.json`)

Expense logged by voice before payments start:

| time | amount | category | description | input |
|---|---|---|---|---|
| 05:40 | ₹3,100 | STOCK_PURCHASE | Kaaikari, Koyambedu | VOICE (Tamil: "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen") |

Payments, injected one by one with `/demo/next-payment`:

| # | transaction_id | time | payer | type | amount | expected action | expected final |
|---|---|---|---|---|---|---|---|
| 1 | TXN-M001-20261115-001 | 06:12 | P10411 | P2M | ₹40 | AUTO | SALE |
| 2 | …-002 | 06:30 | P10057 | P2M | ₹60 | AUTO | SALE |
| 3 | …-003 | 06:58 | P10233 | P2M | ₹120 | AUTO | SALE |
| 4 | …-004 | 07:25 | P10019 | P2M | ₹85 | AUTO | SALE |
| 5 | …-005 | 07:50 | P10388 | P2M | ₹200 | AUTO | SALE |
| 6 | …-006 | 08:40 | P10102 | P2M | ₹150 | AUTO | SALE |
| 7 | …-007 | 09:15 | P10276 | P2M | ₹75 | AUTO | SALE |
| 8 | …-008 | 10:05 | P10040 | P2M | ₹310 | AUTO | SALE |
| 9 | …-009 | 11:20 | P10345 | P2M | ₹45 | AUTO | SALE |
| 10 | …-010 | 12:40 | P10150 | P2M | ₹500 | AUTO | SALE |
| 11 | …-011 | 16:05 | P10077 | P2M | ₹230 | AUTO | SALE |
| 12 | …-012 | 17:10 | P20001 Anbu Mess | P2M | ₹1,200 | AUTO | SALE |
| 13 | …-013 | 18:20 | P10012 | P2M | ₹905 | AUTO | SALE |
| 14 | …-014 | 19:05 | P20001 Anbu Mess | P2M | ₹900 | AUTO | SALE |
| 15 | …-015 | 19:42 | P90001 Lakshmi R | P2P | ₹2,000 | **ASK** (suggested FAMILY) | FAMILY (merchant confirms by voice, says "remember") |

Customer payer IDs (P10xxx) are chosen from payers that already exist in M001's history, so they are not "new payer".

**Expected outputs (asserted by `tests/test_demo_day.py`):**

| moment | collections | business_sales | family | pending | expenses | profit |
|---|---|---|---|---|---|---|
| After expense, before payments | ₹0 | ₹0 | ₹0 | ₹0 (0) | ₹3,100 | −₹3,100 |
| After payment 14 | ₹4,820 | ₹4,820 | ₹0 | ₹0 (0) | ₹3,100 | ₹1,720 |
| After payment 15, before answer | ₹6,820 | ₹4,820 | ₹0 | ₹2,000 (1) | ₹3,100 | ₹1,720 |
| After Murugan answers FAMILY | ₹6,820 | ₹4,820 | ₹2,000 | ₹0 (0) | ₹3,100 | ₹1,720 |

Check: 40+60+120+85+200+150+75+310+45+500+230+1200+905+900 = 4,820.

Spoken Tamil answer at the end must contain exactly the numbers 4,820 / 3,100 / 1,720 / 2,000 (see VOICE_AND_NOTICE.md).

After the answer with `remember_payer: true`: `POST /classify/preview` for P90001, ₹2,000, P2P at 20:30 returns `FAMILY`, `AUTO_CLASSIFY`, source `MERCHANT_CONFIG`, `confidence: null`. This is the "it remembers your instruction" moment. We never call it "the model became 99% sure". The Learning screen shows "Lakshmi: always family (your instruction) · Change".

Without `remember_payer` (also tested): preview returns a **higher confidence than at the first payment, with source `PAYER_MEMORY`** (payer memory moves it toward FAMILY). Whether that next payment is asked or decided automatically depends on the model's score; both are correct. (An earlier version said one answer is never enough; that assumed q = 0.71.)

> If the trained model ever gives a demo sale `ASK`, the test fails. Do not hard-code outcomes and do not tune the model on the demo day. Investigate the feature or generator bug. If it is a genuinely ambiguous payment, replace that scripted payment with a different realistic one and record it in CHANGES.md.

### 3.4 M002 demo day (Telugu)

Expense 05:55, ₹4,200, STOCK_PURCHASE, "Pandlu, Koyambedu", VOICE (Telugu: "Koyambedu lo 4,200 rupayalaku pandlu konnanu").

| # | time | payer | type | amount | expected |
|---|---|---|---|---|---|
| 1 | 07:10 | P1xxxx | P2M | ₹300 | AUTO SALE |
| 2 | 08:05 | P1xxxx | P2M | ₹450 | AUTO SALE |
| 3 | 09:30 | P1xxxx | P2M | ₹600 | AUTO SALE |
| 4 | 10:15 | P1xxxx | P2M | ₹250 | AUTO SALE |
| 5 | 11:40 | P20011 Hotel Sri Sai | P2M | ₹800 | AUTO SALE |
| 6 | 13:20 | P20011 Hotel Sri Sai | P2M | ₹1,200 | AUTO SALE |
| 7 | 15:05 | P1xxxx | P2M | ₹350 | AUTO SALE |
| 8 | 16:45 | P1xxxx | P2M | ₹900 | AUTO SALE |
| 9 | 18:10 | P1xxxx | P2M | ₹700 | AUTO SALE |
| 10 | 19:00 | P1xxxx | P2M | ₹800 | AUTO SALE |
| 11 | 19:50 | P90011 Srinivas | P2P | ₹1,500 | ASK → FAMILY |

Final: collections ₹7,850, sales ₹6,350, family ₹1,500, expenses ₹4,200, profit ₹2,150.
(Customer payer IDs filled in by the generator from M002's existing customers and frozen in the JSON.)

### 3.5 M003

History only (no demo-day script). Used to show `GET /tax-summary` → `gst_treatment: UNKNOWN`, flags `MIXED_CATEGORY_SPLIT_UNKNOWN`, `CA_REVIEW_REQUIRED`.

### 3.6 Demo history (1 Aug to 14 Nov 2026)

Generated by the generator (section 4) with seed 42 and then **replayed through the real classifier and feedback layer** (`python -m data.seed_demo`), with a simulated Murugan answering every question correctly (0% error for demo merchants so the demo ledger is clean). Like condition E, after a FAMILY answer, or a SALE answer on a P2P payment, he chooses "remember" with probability 0.5 (seeded RNG); never for Mani/Jaya/Prabhu, who are not answered. The result is saved as `data/demo/seed.db`. Consequences:

- The Learning screen numbers (questions in the first 7 days vs last 7 days) are real outputs of the system, not typed.
- 3 payments in M001's history are deliberately left `PENDING` (the simulated merchant "did not answer" on 2026-10-29, 2026-10-30, 2026-10-31). They show up as `unresolved` in notice evidence. This is honest and intentional.
- Karthik's payments auto-classify as FAMILY (configured). Selvi triggers the mixed-payer rule after her third confirmation.
- `seed_demo` also writes `data/demo/seed_meta.json`: generator seed, model_version, threshold, git commit, created_at, and sha256 of `seed.db`. `/health` reports `model_version`; if a demo result changes, compare against this file first.

**Release gate (must pass before the demo is accepted, and after any change to generator, features, model or rules):**
Run from the repository root:
```
rm -f data/demo/seed.db data/demo/seed_meta.json backend/naanayam.db
python -m data.generator.run --seed 42
python -m ml.train
python -m data.seed_demo
pytest backend/tests/test_demo_day.py
```
The `rm` line removes only generated files: the demo seed database, its metadata, and the working database (`DB_PATH`, which `/demo/reset` recreates from the seed). Never delete anything else, and never use a wildcard. All rows of 3.3 and 3.4 must pass from this fresh run. Then commit `seed.db`, `seed_meta.json` and the model artifact together.

### 3.7 Sample notice numbers

Sample notice period: 2026-08-01 to 2026-10-31. **Amount questioned = M001's gross UPI receipts for that period** (sum of all PAYMENT_IN, before refunds and reversals), taken from `seed.db` after seeding. Asitha publishes this number on Friday night in `data/demo/notice_numbers.json`; `scripts/make_sample_notice.py` (Asitha) puts it into the sample notice image. If the seed changes, the image must be regenerated (test checks the image's cached extraction against `notice_numbers.json`).

---

## 4. Synthetic data generator (`data/generator/`)

### 4.1 Run

`python -m data.generator.run --seed 42` writes `data/generated/{merchants,payers,payments,refunds,reversals,expenses,family_config}.parquet` plus `labels.parquet` (ground truth: `transaction_id`, `true_label` SALE/FAMILY, `payer_role`) and `label_mix.json` (section 4.3). `family_config.parquet` holds the merchants' family payers configured at setup (M001: Karthik). Ground truth is never loaded by the backend.

The generator also writes the demo-day scripts `data/demo/M001_demo_day.json` and `M002_demo_day.json` (section 3) from the same seed, so a fresh run reproduces them exactly.

Payer IDs: demo merchants (M001–M003) use `P1xxxx` for customers (one shared counter; M001's 12 named demo customers reserved), `P2xxxx` for business buyers and `P9xxxx` for family/friends. Evaluation merchants use 8 digits, `P{merchant number}{nnnnn}` (e.g. `P10100042`), because they have far more walk-in payers than P10001–P19999 can hold. Transaction IDs are numbered in time order within each merchant-day.

Merchants: M001–M003 (demo), M101–M280 (evaluation: M101–M170 train + calibration, M171–M280 test). Period 2026-08-01 to 2026-11-14 inclusive. Demo-day payments for M001/M002 come from the committed scripts, not the generator.

### 4.2 Merchant parameters

| category | customer txns/day (Poisson λ) | median sale | lognormal σ | clip |
|---|---|---|---|---|
| VEGETABLES | 35 | ₹120 | 0.8 | ₹10–₹2,500 |
| FRUITS | 30 | ₹180 | 0.75 | ₹20–₹3,000 |
| FLOWERS | 25 | ₹60 | 0.7 | ₹10–₹1,500 |
| TEA_STALL | 80 | ₹25 | 0.5 | ₹10–₹300 |
| MIXED_KIRANA | 45 | ₹150 | 0.9 | ₹10–₹4,000 |

Evaluation categories keep the original 12/10/6/6/6 proportions within each group: train + calibration M101–M170 = 21 VEGETABLES, 18 FRUITS, 11 FLOWERS, 10 TEA_STALL, 10 MIXED_KIRANA; test M171–M280 = 33 VEGETABLES, 27 FRUITS, 17 FLOWERS, 17 TEA_STALL, 16 MIXED_KIRANA. Each evaluation merchant gets a scale factor U(0.6, 1.5) on λ; demo merchants M001–M003 use 1.0. Sundays ×1.2. Shop hours 05:30–21:30, arrival intensity peaks 06:30–09:30 and 17:00–20:00.

### 4.3 Payer roles (ground truth label in brackets)

| role | label | count per merchant | behaviour |
|---|---|---|---|
| regular customer | SALE | pool of 300 | Zipf repeat (s=1.1); 85% P2M, 15% P2P; 97% PERSONAL; amount from category distribution; 60% rounded to ₹5. **3% of their payments are P2P with a round amount (₹500–₹2,000, rounded to ₹100): paying for a bigger order** |
| walk-in | SALE | new each time, 35% of customer txns | as above |
| business buyer | SALE | 0–3 | every 1–3 days; ₹600–₹3,000; 90% P2M; 70% BUSINESS |
| big one-off order | SALE | ~1 per 14 days | new payer; ₹2,000–₹8,000; 50% P2P; 70% round to ₹500. **Hard negatives: look like family money.** |
| family | FAMILY | 1–4 | PERSONAL; **85% P2P, 15% P2M (the relative scans the shop QR)**; amounts from {500, 1000, 1500, 2000, 3000, 5000}, **25% non-round instead (multiples of ₹50 that are not multiples of ₹100, ₹500–₹5,000, e.g. ₹750, ₹1,250, ₹2,350)**; every 5–30 days; **65% after 18:00, 35% during shop hours before 18:00**. (Karthik, M001, stays as in 3.2.) |
| friend / loan repayment | FAMILY | 0–2 | P2P; round, **30% non-round (as for family)**; 2–4 times over the period |
| mixed relative | 30% SALE / 70% FAMILY | 1 in 3 merchants | SALE ones are non-round P2M, FAMILY ones round P2P |
| **credit-settlement customer** | **SALE** | **3–8** | **A regular who settles a tab weekly (every 6–8 days) or monthly (every 28–32 days) by P2P; round ₹500–₹3,000 (rounded to ₹100); 70% after 18:00. Hard negatives: look like family money.** |

Overall label mix targets about **0.5% FAMILY by count** (the role behaviour above gives roughly one family transfer a week per merchant). FAMILY is a much larger share **by value**, because family transfers are large. The generator prints and saves both, overall and per split (demo, train+calibration, test merchants, test set), in `data/generated/label_mix.json`; `seed_demo` copies them into `seed_meta.json` and the evaluation into `latest.json` as `label_mix.count_share` and `label_mix.value_share` (value share = sum of FAMILY amounts / sum of all amounts). It also prints the number of FAMILY payments in the test set (target ≥ 500) and per-role counts; check them.

### 4.4 Refunds, reversals, expenses
- Refunds: 0.3% of SALE payments, within 0–2 days, 50% full / 50% partial (20–80%).
- Reversals: 0.1% of all payments, within 0–1 day, only on payments with no refund.
- Expenses (M001–M003 only): daily stock purchase 05:00–06:30 (VEGETABLES ₹2,500–₹4,500, FRUITS ₹3,000–₹5,500, KIRANA twice weekly ₹8,000–₹20,000), weekly TRANSPORT ₹300–₹800, PACKAGING twice a month ₹200–₹500, monthly RENT ₹6,000 on the 5th. `input_source` 70% VOICE, 30% MANUAL.

### 4.5 Merchant answer simulation
`simulate_answer(true_label, error_rate)`: returns the true label, flipped with probability `error_rate`. Evaluation uses 0.02. Demo seeding uses 0.0. Seeded RNG per merchant.

---

## 5. Classifier (`backend/app/classifier/`, training in `ml/`)

### 5.1 Features (computed only from that merchant's data strictly before the payment time; no labels used)

| feature | definition |
|---|---|
| log_amount | ln(amount in rupees) |
| amt_ratio_median | amount / merchant's median payment over the previous 14 days (default category median if < 50 payments) |
| is_round_100, is_round_500, is_round_1000 | amount divisible by ₹100 / ₹500 / ₹1,000 |
| is_p2p | payment_type == P2P |
| is_business_vpa | payer_vpa_kind == BUSINESS |
| hour, hour_sin, hour_cos | IST hour |
| is_evening | hour ≥ 18 |
| day_of_week, is_sunday | |
| is_new_payer | payer never paid this merchant before |
| payer_prior_count | count of previous payments by this payer to this merchant |
| payer_prior_p2p_share | share of those that were P2P (0 if new) |
| payer_amt_ratio | amount / payer's mean previous amount (1 if new) |
| days_since_payer_last | days since this payer last paid (999 if new) |
| payer_round_share | share of payer's previous payments that were round to ₹100 |
| category one-hot | 5 columns |

Merchant-confirmed labels are **not** features. They are used only by the feedback layer (section 6). This keeps "baseline vs with feedback" a clean comparison.

One function `features.build(payment, history_df)` is used in training, evaluation and the live API. Test: same payment gives identical feature vector in both paths.

### 5.2 Model
- LightGBM binary classifier, target = FAMILY. Fallback if LightGBM will not install: `sklearn.ensemble.HistGradientBoostingClassifier`. Params: `num_leaves=31, learning_rate=0.05, n_estimators=400, min_child_samples=40, class_weight="balanced"` (then calibrated).
- Training data: M101–M170, payments 2026-08-01 to 2026-10-01.
- Saved to `ml/artifacts/{model_version}.joblib` with feature list, calibrator, threshold and training metadata. Committed (it is small).

### 5.3 Calibration
- Calibration: isotonic regression fitted on **out-of-fold** raw scores over the whole train + calibration period (M101–M170, 2026-08-01 to 2026-10-15). 5 folds grouped by merchant; each fold model is trained like the final model (train period, other merchants) and scores the held-out merchants. → `q_model` = calibrated p(FAMILY).
- Calibration set (for choosing τ): M101–M170, 2026-10-02 to 2026-10-15.
- Report ECE (10 equal-width bins) before and after calibration.

### 5.4 Threshold selection
- Grid τ ∈ {0.80, 0.81, …, 0.99, 0.995, 0.998, 0.999}. On the calibration set only, run the full decision procedure (5.6) **without** feedback (condition C), merchant answers taken as correct.
- Chosen τ **minimises silent errors** (family counted as sale + sale removed as family) subject to: questions ≤ 1.0 per merchant per day, precision_auto ≥ 0.95, τ ≥ `CONF_THRESHOLD` (default 0.90). Ties: the lower τ. Stored in the model artifact with the full calibration-set table (τ, coverage, precision_auto, questions/day, silent errors, family recall), which is also copied into `latest.json`. `/health` reports the effective τ.
- Changing `CONF_THRESHOLD` in `.env` lets us show the trade-off live (higher τ → more questions, higher precision). The evaluation file includes the whole curve so the trade-off is shown, not just one point.

### 5.5 Reasons (fixed list, max 4 shown, in this priority order)

| code (internal) | English text |
|---|---|
| CONFIGURED_FAMILY | "Marked as family by merchant" |
| CONFIGURED_CUSTOMER | "Marked as customer by merchant" |
| FAMILY_GUARDRAIL | "Looks like a shop sale from a family payer" (rule 5d) |
| CUSTOMER_GUARDRAIL | "Looks like family money from a customer" (rule 1b guardrail) |
| MIXED_PAYER | "This person has paid for both shop and family before" |
| FIRST_TIME_LARGE | "First payment from this person, and large" |
| FAMILY_NEEDS_CONFIRMATION | "Family money is only excluded after the merchant confirms" |
| PAYER_CONFIRMED_FAMILY | "Merchant confirmed this person's money as family before" |
| PAYER_CONFIRMED_SALE | "Merchant confirmed this person's payments as sales before" |
| NEW_PAYER | "New payer" |
| P2P | "P2P transfer" |
| ROUND_AMOUNT | "Round amount" |
| LARGER_THAN_USUAL | "Larger than usual sale" (amt_ratio_median ≥ 5) |
| BUSINESS_VPA | "Business UPI ID" |
| REGULAR_CUSTOMER | "Regular customer" (payer_prior_count ≥ 5, mostly P2M) |
| TYPICAL_AMOUNT | "Typical sale amount" (0.3 ≤ amt_ratio_median ≤ 3) |

Reasons are rule-derived from feature values, not from SHAP. They describe the inputs; they do not claim to explain the model exactly. Frontend label: "Signals".

### 5.6 Decision procedure (exact order)

```
0. q = q_model(features)        # calibrated p(FAMILY), computed for EVERY payment, before any configuration
1. If payer in merchant_family_payers:
       guardrail 5d: payment_type == P2M AND amount not round to ₹100 AND q <= 0.02
           -> ASK_MERCHANT, source=RULE, suggested = model's (SALE), confidence = max(q, 1-q), kind MODEL,
              reason "Looks like a shop sale from a family payer".  STOP.
       otherwise FAMILY, AUTO_CLASSIFY, source=MERCHANT_CONFIG, confidence = null, confidence_kind = NONE.  STOP.
   (A configured rule, not a probability. The merchant can correct any such payment to SALE;
    the API then offers to remove the payer from the family list.)
1b. If payer in merchant_customer_payers:
       guardrail: payment_type == P2P AND amount round to ₹500 AND q >= 0.98
           -> ASK_MERCHANT, source=RULE, suggested = model's (FAMILY), confidence = max(q, 1-q), kind MODEL,
              reason "Looks like family money from a customer".  STOP.
       otherwise SALE, AUTO_CLASSIFY, source=MERCHANT_CONFIG, confidence = null, confidence_kind = NONE.  STOP.
   (A payer is never in both lists; see section 6.)
2. q as computed in step 0
3. Payer memory (section 6): n_family, n_sale from merchant-confirmed feedback for this payer at this merchant.
   p = (k*q + n_family) / (k + n_family + n_sale)   # k from the model artifact (5.7); if n_family + n_sale == 0 then p = q
   source = PAYER_MEMORY if n_family + n_sale > 0 else MODEL
4. suggested = FAMILY if p >= 0.5 else SALE
   confidence = max(p, 1 - p)
   action = AUTO_CLASSIFY if confidence >= τ else ASK_MERCHANT
5. Override rules (each forces ASK_MERCHANT, source=RULE, keeps suggested and confidence):
   a. Mixed payer: n_family + n_sale >= 3 and min(n_family, n_sale) / (n_family + n_sale) >= 0.25
   b. First-time large: is_new_payer and amount >= ₹5,000
   c. Family needs confirmation: suggested == FAMILY and n_family == 0
      (Naanayam never removes money from business income without the merchant having said so at least once for this payer.)
6. classification = suggested if AUTO_CLASSIFY else PENDING
```

Rule 5c is why Lakshmi's first ₹2,000 is always asked, regardless of the exact model score. It is also the honest answer to "what if the model is wrong about family money": excluding income is the costly error, so we never do it silently for an unconfirmed payer.

---

## 6. Feedback layer (`backend/app/feedback/`)

**Configured family (explicit memory) vs payer memory (soft):** configured family is the merchant's standing instruction and skips the model (rule 1). Payer memory is the soft Bayesian pull below. Both are shown separately on the Learning screen and in the evaluation (section 11).

**What counts as a label:** only rows in `feedback` (merchant answers via tap or voice). Auto-classifications are never used.

**Counting:** for (merchant, payer), take the **latest** feedback row per transaction (if Murugan changed his mind on one payment, only the last answer counts). `n_family` = count FAMILY, `n_sale` = count SALE. Reversed payments are excluded.

**Formula:** as in 5.6 step 3. Worked examples (k = 2):

| q_model | n_family | n_sale | p | confidence | action at τ=0.90 |
|---|---|---|---|---|---|
| 0.71 | 0 | 0 | 0.71 | 0.71 | ASK (and rule 5c) |
| 0.71 | 1 | 0 | 0.807 | 0.807 | ASK |
| 0.71 | 2 | 0 | 0.855 | 0.855 | ASK |
| 0.71 | 4 | 0 | 0.903 | 0.903 | AUTO FAMILY |
| 0.30 | 3 | 0 | 0.72 | 0.72 | ASK |
| 0.10 | 0 | 3 | 0.04 | 0.96 | AUTO SALE |
| 0.60 | 2 | 2 | 0.533 | 0.533 | ASK (mixed payer rule) |

**Explicit memory:** when the merchant confirms FAMILY with `remember_payer: true` (voice: "aamaa, eppavum veettu panam dhaan" / tap "Always family"), the payer is added to `merchant_family_payers` with `added_via=CONFIRMATION`. From then on rule 1 applies. Removing a payer from family is done via `PUT /merchants/{id}`. Neither rewrites past ledger entries.

**Customer memory:** after a SALE answer on a **P2P** payment the UI offers "Remember as customer"; confirming SALE with `remember_payer: true` adds the payer to `merchant_customer_payers` (`added_via=CONFIRMATION`). From then on rule 1b applies. The backend rejects SALE + remember on a non-P2P payment (422).

**One list only:** remembering a payer in one list removes them from the other in the same transaction (the confirm response says `"moved_from": "FAMILY"` or `"CUSTOMER"`). `PUT /merchants/{id}` that would leave a payer in both lists → 422. Configuration changes never rewrite ledger history.

**Not feedback:** no retraining per answer. Retraining the global model is an offline step (`python -m ml.train`) and is out of scope for the demo.

---

## 7. Ledger and finance

### 7.1 Ledger rules
| event | entries written |
|---|---|
| New payment | `PAYMENT_IN` (amount, classification SALE/FAMILY/PENDING, source, confidence) |
| Merchant answers or corrects | `RECLASSIFICATION` (same amount, new classification, `classification_source=MERCHANT_CONFIRMED`, `supersedes_entry_id` = latest classification entry for that payment) |
| Refund | `REFUND_OUT` (refund amount, `source_type=REFUND`, `source_id=refund_id`) |
| Reversal | `REVERSAL` (full amount, `source_type=REVERSAL`, `source_id=transaction_id`) |
| Expense | `EXPENSE` |
| Expense void | `EXPENSE_VOID` (same amount, `supersedes_entry_id` = the EXPENSE entry) |
| Payer added to family later | nothing (affects future payments only) |

Current classification of a payment = classification on its latest `PAYMENT_IN`/`RECLASSIFICATION` entry (highest seq).

Each write (domain row + ledger entry + prediction/question) happens in **one SQLite transaction**. If anything fails, nothing is written.

### 7.2 Hash chain
```
canonical = json.dumps({
  "merchant_id", "seq", "entry_type", "source_type", "source_id", "supersedes_entry_id",
  "amount_paise", "classification", "classification_source", "confidence",
  "expense_category", "effective_at", "created_at", "prev_hash"
}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
hash = sha256(canonical.encode("utf-8")).hexdigest()
```
- `prev_hash` of seq 1 = `"0" * 64`. Each merchant has its own chain.
- Writes for one merchant are serialized (a per-merchant lock, or `BEGIN IMMEDIATE`), so seq has no gaps.
- **Verify:** walk seq 1..N; recompute each hash; check `prev_hash == previous hash`. First failure → `TAMPERED` with `hash_mismatch` (row content changed) or `prev_hash_mismatch` (row inserted/deleted/reordered).
- **What we claim:** tamper-evident audit trail. It shows records were not edited after being written. It does **not** prove the records are true, and without an external anchor someone with DB access could rebuild the whole chain. Say this if asked. (Future: publish the daily head hash to the merchant via SMS/WhatsApp so it is anchored outside our DB.)

### 7.3 Financial definitions (period P = set of IST dates)

Payments are attributed to the date of the **original payment**. Refunds and reversals attach to their payment (state "as of now"). Expenses are attributed to the expense timestamp.

**Disclosure (required):** because of this convention, a past day's totals can change when a later refund or reversal happens. Every summary, export and notice evidence carries `as_of` and the `attribution_note`. We chose it because it keeps the reconciliation identity exact for any period; a cash-basis view (refund on refund date) is a later option.

**Refund/reversal rule:** a payment can have refunds or a reversal, never both (API returns 409). The generator respects this.

For each payment with timestamp in P: g = amount, r = sum of its refunds, reversed = has reversal.

| bucket | rule |
|---|---|
| total_collections | Σ g (gross, every payment) |
| reversals | Σ g where reversed |
| refunds | Σ r where not reversed (any classification) |
| business_sales | Σ (g − r) where not reversed and current = SALE |
| family_transfers | Σ (g − r) where not reversed and current = FAMILY |
| pending | Σ (g − r) where not reversed and current = PENDING (count = number of such payments) |
| expenses | Σ EXPENSE amounts with timestamp in P, excluding voided ones |
| profit | business_sales − expenses ("recorded profit"; technical name: recorded operating surplus). Scope note always shown: UPI only, expenses the merchant entered, no cash sales, no stock changes |

**Identity (checked on every summary, `reconciliation_ok`):**
`total_collections = business_sales + family_transfers + pending + refunds + reversals`

Notes:
- Pending money is not profit. The voice answer says "N payments not yet confirmed".
- Profit can be negative (morning, after stock purchase). Display "−₹3,100". Voice says "nashtam" (loss) via template.
- Cash sales are not in the system. Every output that summarises income says so ("UPI payments only").
- Duplicates: the only duplicate key is `transaction_id` (UPI IDs are unique). Two separate payments with the same payer and amount a minute apart are two real payments. A bank duplicate shows up as a reversal.

### 7.4 Idempotency details
- `payload_hash` = sha256 of canonical JSON of the request body.
- Same key + same hash → return stored response (`200`, `idempotent_replay: true`). Same key + different hash → `409 DUPLICATE_CONFLICT` with the first differing field in `details.field`.
- Confirm is idempotent on (transaction_id, confirmed_category) when it is already the current merchant-confirmed classification.
- Tests: send each demo payment twice → totals unchanged; send one with a changed amount → 409; double-tap expense save (same client_request_id) → one expense.

---

## 8. GST treatment and tax summary

| business_category | gst_treatment | basis text |
|---|---|---|
| VEGETABLES | EXEMPT_LIKELY | "Merchant configured category VEGETABLES (fresh vegetables are generally GST-exempt). Not inferred from payments." |
| FRUITS | EXEMPT_LIKELY | same pattern, "fresh fruits" |
| FLOWERS | EXEMPT_LIKELY | same pattern, "fresh flowers" |
| TEA_STALL | TAXABLE_LIKELY | "Merchant configured category TEA_STALL (prepared food and drinks are generally taxable). Not inferred from payments." |
| MIXED_KIRANA | UNKNOWN | "Mixed goods. The split between exempt and taxable sales cannot be known from UPI payments." |

- `ca_review_required` is always true. Flag `CA_REVIEW_REQUIRED` always present.
- `MIXED_KIRANA` adds `MIXED_CATEGORY_SPLIT_UNKNOWN`. No estimate is ever computed from amounts or purchases.
- Category is what the merchant declared. The UI shows "Declared by merchant" next to it.
- Tax summary amounts use 7.3 for the period.

---

## 9. Notice evidence (`GET /notices/{id}/evidence`)

Inputs: the stored notice fields (extracted) + the ledger.

1. Period = extracted `period_start`..`period_end`. If either is `NOT_FOUND`, return `422 VALIDATION_ERROR` with message "Could not read the notice period. Evidence not generated." The frontend shows that error and does **not** build evidence. No manual period entry (out of scope). Only the committed sample notice is supported in the demo.
2. `ledger_view` = 7.3 buckets for that period, each tagged `DERIVED_FROM_LEDGER` with `entry_count`.
3. `amount_questioned` = extracted value, tagged `EXTRACTED_FROM_NOTICE`.
4. `difference_vs_notice` = amount_questioned − ledger total_collections. If 0: explanation "The notice amount matches total UPI collections in the ledger. The breakdown below shows how much of it was business sales." If not 0: "The notice amount differs from ledger collections by X. Possible reasons: payments to other accounts, or cash. A CA must check."
5. `family_transfer_examples`: up to 5 FAMILY payments in the period, largest first, with `confirmed_by` = `MERCHANT_CONFIG` or `MERCHANT_CONFIRMED` (from the payment's current classification source).
6. Warnings: always the three in the contract; add "N payments in this period are still unconfirmed" if pending > 0; add "Ledger integrity check failed" if verify is not VALID.
7. For the committed sample (M001), expected: difference 0, unresolved count 3 (see 3.6), family examples include Karthik.

---

## 10. Credit passport (P4, show only)

Months = Aug, Sep, Oct 2026 (complete months before DEMO_DATE). Per month, 7.3 buckets:
- `raw_collections` = total_collections
- `refunds_reversals` = refunds + reversals
- `family_transfers`
- `business_sales`
- `expenses`
- `recorded_income` = business_sales (the "recorded business income")
- `unresolved_count` = pending count

`share_of_collections_that_were_business_sales` = Σ business_sales / Σ raw_collections, 3 dp.
Label is fixed: "Recorded business income summary. Not verified income. Not a credit decision." No score, no limit, no eligibility.

---

## 11. Evaluation protocol (`ml/evaluate.py`)

### 11.1 Splits
| set | merchants | period | used for |
|---|---|---|---|
| Train | M101–M170 | 2026-08-01 – 2026-10-01 | fitting |
| Calibration | M101–M170 | 2026-10-02 – 2026-10-15 | isotonic + choosing τ |
| Test | **M171–M280 (110, never seen)** | **2026-10-16 – 2026-11-14 (after training period)** | all reported numbers |

Both a merchant holdout and a time holdout.

### 11.2 Leakage rule (enforced, tested)
Features for a payment at time t use **only that merchant's payments with timestamp < t** (strictly earlier; ties broken by transaction_id order, earlier IDs only). Implementation: the replay walks payments in time order and appends each payment to the history **after** computing its features. No pandas groupby over the full table. Test: for 200 random test payments, recompute features from a history truncated at t and assert they are identical; and assert that shuffling all future payments does not change any feature.

Test merchants' payments before 10-16 are used as history (observable without labels). No labels from test merchants are used except simulated answers inside the replay.

### 11.3 Conditions (all run the **complete** decision procedure of 5.6, same model, same τ, same answer RNG)
| condition | payer memory | remember instruction | purpose |
|---|---|---|---|
| A. Always SALE | n/a | n/a | trivial baseline: shows why accuracy alone misleads (over 99% "accurate" by count, 0 family found) |
| B. Naive rule | n/a | n/a | P2P + round ₹100 → FAMILY, else SALE |
| C. Model, no feedback | off (n=0 always) | off | baseline system: ASK items answered (2% error) but answers not stored |
| D. Model + payer memory | on | off | soft learning only |
| E. Full system (as demoed) | on | on | after a FAMILY answer the simulated merchant chooses "remember" (family list) with probability 0.5, and after a SALE answer on a **P2P** payment chooses "Remember as customer" (customer list) with probability 0.5. One list per payer (remembering in one removes from the other). Guardrails 5d and 1b apply. Merchant answer error 2%. For mixed relatives this produces real errors, which is the point: it measures the cost of the shortcut |

τ is chosen on the calibration set with condition C rules. Because D and E add feedback and rules after τ is chosen, **their precision is measured, not assumed**: we report precision for every condition separately.

Every condition starts test merchants with empty memory and no configured family at 10-16.

### 11.4 Metrics (per condition)
| metric | definition |
|---|---|
| precision_auto | correct AUTO decisions / all AUTO decisions (for A and B: all decisions) |
| precision_auto_by_source | split by MODEL, PAYER_MEMORY, MERCHANT_CONFIG |
| coverage | AUTO decisions / all payments |
| questions_per_merchant_per_day | ASK count / (merchants × days) |
| overall_accuracy | final labels (AUTO decision or simulated answer) vs ground truth |
| family_recall_final | true FAMILY payments that end as FAMILY |
| silent_family_errors | true SALE auto-labelled FAMILY (income silently removed; the costly error) |
| silent_sale_errors | true FAMILY auto-labelled SALE |
| config_errors | errors made by MERCHANT_CONFIG decisions (condition E) |
| questions_per_day_by_week | 4 weekly values |
| pr_coverage_curve | condition C precision_auto and coverage for τ 0.50–0.99 |
| confusion_matrix_auto | AUTO decisions only |
| calibration | ECE + 10 bins of q_model on test |

**Headline metrics** (shown first): "family money found X of N" (family_recall_final), "income wrongly removed Y of M" (true SALE payments whose final label is FAMILY, split into silent and merchant-answer errors), and questions per merchant per day. precision_auto and precision by source are secondary and always shown next to the always-SALE baseline.

**Family-specific metrics are reported as counts with their denominators, not only rates**, because the FAMILY class is small: e.g. `"family_recall_final": {"count": 503, "of": 512, "rate": 0.9824}` and `"silent_family_errors": {"count": 6, "of": 152525}`. Denominators: family_recall_final and silent_sale_errors = all true FAMILY payments; silent_family_errors = all true SALE payments; config_errors = all MERCHANT_CONFIG decisions. This applies to family_recall_final, silent_family_errors, silent_sale_errors and config_errors. The screen shows "9 of 31,200", never a bare rate.

Also: label mix (`label_mix.count_share`, `label_mix.value_share`), number of test payments, answer error rate.

### 11.5 Output
`data/eval/runs/{run_id}.json` and `data/eval/latest.json`: the contract shape, where `baseline` = condition C and `with_feedback` = condition E, plus a `conditions` object with all five (A–E) and every metric above, `seed`, `git_commit`, `threshold`. The Learning screen (Asitha) shows A, C, E side by side and the curve.

### 11.6 What we are allowed to say
- "On synthetic data from 110 merchants the model never saw, over a later 30-day period: the full system decided X% of payments without asking at Y% precision, silently removed income in Z cases, and questions per day fell from A to B over four weeks."
- Always "synthetic". Never "accuracy" alone; always precision with coverage, and the always-SALE baseline next to it.
- Configured family decisions are "the merchant's instruction", reported with their own error count.
- Any headline precision is shown with its split by source (model alone, payer memory, merchant instruction) so the answer to "how much of this is ML?" is on screen.
- No real-world performance claims.

---

## 12. Backend test list (Asitha; core ones before Saturday 12:00)

1. `money.display` cases.
2. Idempotent payment replay, conflict 409, expense double save, edited draft = new expense.
3. Demo day M001 and M002: every expected row in 3.3 / 3.4.
4. Reconciliation identity on random periods over all seeded merchants.
5. Refund > remaining → 409. Reversal after refund → 409. Refund after reversal → 409. Confirm after reversal → 409.
6. Hash chain VALID on seed; `/demo/tamper` → TAMPERED at the right entry; `/demo/reset` → VALID; demo endpoints 404 when `ENABLE_DEMO_TOOLS=false`.
7. Feedback examples in section 6 (pure function).
8. Rule 5c: FAMILY suggestion with n_family = 0 is always ASK.
9. Feature parity between training and API paths.
10. **Leakage test** (11.2).
11. Confirm with a `question_id` from another transaction → 409 `QUESTION_MISMATCH`.
12. MERCHANT_CONFIG decisions have `confidence: null`.
13. Tax summary M001 EXEMPT_LIKELY, M003 UNKNOWN with no split amounts.
14. Notice evidence for sample: difference 0, unresolved 3; missing period → 422 and no evidence.
15. No `UPDATE`/`DELETE` on append-only tables (grep test, `demo/tamper.py` excluded).
16. Cache identity: a live upload whose bytes differ from a demo clip never returns the clip's transcript; `demo_key` with wrong bytes → 422.
