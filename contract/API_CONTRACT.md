# Naanayam API Contract (v1.1, frozen 13 Nov 2026 after review)

> v1.1 changes: `confidence` null for `MERCHANT_CONFIG` + new `confidence_kind`; questions bound to `question_id`; correction workflow; refund/reversal rule; `recognition_mode` on transcribe; template-only money speech; `as_of` + scope note on summaries; demo tools gated by `ENABLE_DEMO_TOOLS`; `VITE_API_BASE`.

> Owner: Asitha. Do not change names, enums, status codes or shapes. Request changes in `contract/CHANGES.md`.
> Example IDs are illustrative unless they appear in the demo fixtures in `docs/DATA_AND_LOGIC.md` section 3.

---

## 0. Conventions

| Rule | Detail |
|---|---|
| Base URL | `http://localhost:8000/api` |
| Format | JSON (`Content-Type: application/json`), except audio/file uploads (`multipart/form-data`) |
| Money | `amount_paise`: integer paise (₹4,820 = `482000`). Every money field also has `*_display`: backend-formatted string in Indian format (`"₹4,820"`, `"₹1,20,000"`). Frontend never formats or computes money. |
| Time | ISO 8601 with IST offset: `"2026-11-15T19:42:10+05:30"`. Dates: `"2026-11-15"`. A day = IST calendar day. |
| "Today" | Backend clock = `DEMO_DATE` env (default `2026-11-15`). Endpoints with optional `date` default to today. |
| IDs | `merchant_id` `M001`; `payer_id` `P10001`; `transaction_id` `TXN-M001-20261115-015`; `expense_id` `EXP-M001-000231`; `ledger_entry_id` `LE-M001-000874`; `question_id` `Q-M001-000057`; `notice_id` `NTC-M001-001`; `audio_id` `AUD-<sha256 first 16 hex>` |
| Success | Plain JSON object (no wrapper). `200` for reads and idempotent replays, `201` for new resources. |
| Validation | The backend revalidates every field of every write (amount > 0 and ≤ ₹5,00,000 for expenses, enums, merchant exists, question belongs to the transaction and merchant). Frontend validation is a convenience only. |
| Lists | Every list response with `count` reports the total number of items matching the filters, before `limit`/`offset`; `items` is the requested page. |
| Confidence format | API: JSON number rounded to 4 dp (e.g. `0.98`, `0.7123`) or `null`. Database and hash canonicalisation: 4-decimal string (`"0.9800"`) or null. Conversion happens only in the repository layer: `f"{x:.4f}"` on write, `float(s)` on read. The fixture ledger hashes were computed this way. |
| Confidence display | The API returns the real number. The frontend shows a confidence ≥ 0.995 as ">99%", never "100%"; `null` shows as "Your instruction". |
| Confidence | `confidence` is a calibrated model probability (optionally adjusted by payer memory) when `confidence_kind` = `MODEL`. When the decision comes from the merchant's configuration, `confidence` = `null` and `confidence_kind` = `NONE`. The UI shows "Your instruction" instead of a percentage. |
| Errors | Always this shape, with the HTTP status below: |

```json
{
  "error": {
    "code": "DUPLICATE_CONFLICT",
    "message": "transaction_id TXN-M001-20261115-015 already exists with a different amount",
    "details": { "transaction_id": "TXN-M001-20261115-015", "field": "amount_paise" }
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `BAD_REQUEST` | Malformed JSON, wrong content type |
| 404 | `NOT_FOUND` | Unknown merchant, transaction, expense, notice, ledger entry, audio |
| 409 | `DUPLICATE_CONFLICT` | Same idempotency key re-sent with different content |
| 409 | `INVALID_STATE` | Action not allowed in current state (refund larger than remaining amount, voiding a voided expense, etc.) |
| 422 | `VALIDATION_ERROR` | Field missing, wrong type, enum not allowed, amount ≤ 0 |
| 503 | `SARVAM_UNAVAILABLE` | Sarvam call failed or timed out (live / cache_first modes) |
| 503 | `CACHE_MISS` | `DEMO_MODE=cache_only` and no cached response for this exact input |
| 500 | `INTERNAL_ERROR` | Anything else (log it) |

### Enums (exact strings)

| Enum | Values |
|---|---|
| `language` | `ta`, `te`, `en` |
| `business_category` | `VEGETABLES`, `FRUITS`, `FLOWERS`, `TEA_STALL`, `MIXED_KIRANA` |
| `payment_type` | `P2M` (paid to merchant QR), `P2P` (paid to merchant's UPI number/ID person-to-person) |
| `classification` | `SALE`, `FAMILY`, `PENDING` |
| `confirmable_category` | `SALE`, `FAMILY` |
| `action` | `AUTO_CLASSIFY`, `ASK_MERCHANT` |
| `classification_source` | `MERCHANT_CONFIG`, `PAYER_MEMORY`, `MODEL`, `RULE`, `MERCHANT_CONFIRMED` |
| `entry_type` | `PAYMENT_IN`, `RECLASSIFICATION`, `REFUND_OUT`, `REVERSAL`, `EXPENSE`, `EXPENSE_VOID` |
| `expense_category` | `STOCK_PURCHASE`, `TRANSPORT`, `PACKAGING`, `RENT`, `WAGES`, `UTILITIES`, `OTHER` |
| `input_source` | `VOICE`, `MANUAL`, `BILL` |
| `confirmation_channel` | `TAP`, `VOICE` |
| `question_status` | `OPEN`, `ANSWERED` |
| `intent` | `LOG_EXPENSE`, `ASK_DAILY_PROFIT`, `CONFIRM_TRANSACTION`, `UNKNOWN` |
| `gst_treatment` | `EXEMPT_LIKELY`, `TAXABLE_LIKELY`, `UNKNOWN` |
| `field_origin` | `EXTRACTED_FROM_NOTICE`, `DERIVED_FROM_LEDGER`, `NOT_FOUND` |
| `confidence_kind` | `MODEL`, `NONE` |
| `recognition_mode` | `LIVE` (Sarvam called now), `CACHED_LIVE` (same audio bytes transcribed earlier by Sarvam), `RECORDED_DEMO` (a committed demo clip, verified by audio hash) |

---

## 1. Health and demo control

All `/demo/*` endpoints exist only when `ENABLE_DEMO_TOOLS=true`; otherwise they return `404 NOT_FOUND`. They only ever act on a database restored from `data/demo/seed.db`.

### GET `/health`
`200`
```json
{ "status": "ok", "demo_mode": "cache_only", "demo_date": "2026-11-15", "db": "ok", "model_version": "clf-2026-11-14-01", "threshold": 0.9, "demo_tools": true, "tampered": false }
```

### POST `/demo/reset`
Restores the database to the committed seed state: all history before `DEMO_DATE`, nothing on `DEMO_DATE` (demo-day payments are injected live). Clears feedback created on `DEMO_DATE`.

Request: `{}` → `200`
```json
{ "status": "reset", "merchants": ["M001", "M002", "M003"], "demo_date": "2026-11-15", "pending_demo_payments": { "M001": 15, "M002": 11 } }
```

### POST `/demo/next-payment`
Injects the next scripted demo-day payment for a merchant, through exactly the same code path as `POST /payments`.

Request:
```json
{ "merchant_id": "M001" }
```
`201`: same body as `POST /payments` response, plus `"demo_index": 15, "demo_remaining": 0`. When the payment is ASK, the frontend opens **this** `question_id` directly (never "the first open question": the seed history contains older open questions).
`409 INVALID_STATE` when the script is finished.

### GET `/demo/script?merchant_id=M001`
`200`: the scripted demo-day payments and the expected outcome of each (from `data/demo/`), for the demo control panel.
```json
{
  "merchant_id": "M001",
  "items": [
    { "demo_index": 1, "transaction_id": "TXN-M001-20261115-001", "time": "06:12", "payer_name": "Customer", "amount_display": "₹40", "expected_action": "AUTO_CLASSIFY", "expected_classification": "SALE", "injected": false }
  ]
}
```

---

## 2. Merchants

### GET `/merchants`
`200`
```json
{ "merchants": [ { "merchant_id": "M001", "display_name": "Murugan Kaaikari Kadai", "owner_name": "Murugan", "business_category": "VEGETABLES", "preferred_language": "ta" } ] }
```

### GET `/merchants/{merchant_id}`
`200`
```json
{
  "merchant_id": "M001",
  "display_name": "Murugan Kaaikari Kadai",
  "owner_name": "Murugan",
  "city": "Chennai",
  "business_category": "VEGETABLES",
  "preferred_language": "ta",
  "family_payers": [ { "payer_id": "P90002", "payer_name": "Karthik", "relation_label": "Thambi (brother)" } ],
  "customer_payers": [ { "payer_id": "P10411", "payer_name": "Senthil K" } ],
  "created_at": "2026-08-01T05:00:00+05:30"
}
```

### PUT `/merchants/{merchant_id}`
Partial update. Only these fields:
```json
{ "preferred_language": "ta", "business_category": "VEGETABLES", "family_payer_ids": ["P90002", "P90001"], "customer_payer_ids": ["P10411"] }
```
`200`: full merchant object. Each list field, when present, **replaces** that configured list. Changes affect **future** classifications only; they never rewrite history. `422` for unknown payer IDs (`details.unknown`) and when the result would put a payer in both lists (`details.overlap`). Moving a payer between lists is done by removing them from one list in the same request, or by the confirm flow below.

---

## 3. Payments

### POST `/payments`
Registers one incoming payment, classifies it, writes a `PAYMENT_IN` ledger entry, and creates a question if needed. **Idempotent on `transaction_id`.**

Request:
```json
{
  "transaction_id": "TXN-M001-20261115-015",
  "merchant_id": "M001",
  "payer_id": "P90001",
  "payer_name": "Lakshmi R",
  "payer_vpa_kind": "PERSONAL",
  "amount_paise": 200000,
  "payment_type": "P2P",
  "timestamp": "2026-11-15T19:42:10+05:30",
  "description": null
}
```
`payer_vpa_kind`: `PERSONAL` or `BUSINESS` (whether the payer's UPI ID is a personal or business handle; simulated).

`201` (new) or `200` (identical replay, `"idempotent_replay": true`):
```json
{
  "transaction_id": "TXN-M001-20261115-015",
  "merchant_id": "M001",
  "amount_paise": 200000,
  "amount_display": "₹2,000",
  "classification": "PENDING",
  "suggested_classification": "FAMILY",
  "confidence": 0.71,
  "confidence_kind": "MODEL",
  "action": "ASK_MERCHANT",
  "classification_source": "RULE",
  "reasons": ["Family money is only excluded after the merchant confirms", "New payer", "P2P transfer", "Round amount"],
  "question_id": "Q-M001-000057",
  "ledger_entry_id": "LE-M001-000874",
  "idempotent_replay": false
}
```
For `AUTO_CLASSIFY`: `classification` = `SALE` or `FAMILY`, `question_id` = `null`.
For `MERCHANT_CONFIG` decisions: `confidence` = `null`, `confidence_kind` = `NONE`.
(Lakshmi's first payment is `RULE`: the model leans FAMILY, and rule 5c in DATA_AND_LOGIC forces a question.)
`reasons`: up to 4 short English strings from a fixed list (see `docs/DATA_AND_LOGIC.md` 5.5); frontend shows them; voice does not read them.

Errors: `409 DUPLICATE_CONFLICT` if same `transaction_id` with any different field; `422` for amount ≤ 0 or unknown merchant/enums.

### GET `/payments/{transaction_id}`
`200`
```json
{
  "transaction_id": "TXN-M001-20261115-015",
  "merchant_id": "M001",
  "payer_id": "P90001",
  "payer_name": "Lakshmi R",
  "payer_vpa_kind": "PERSONAL",
  "payment_type": "P2P",
  "amount_paise": 200000,
  "amount_display": "₹2,000",
  "timestamp": "2026-11-15T19:42:10+05:30",
  "description": null,
  "current_classification": "FAMILY",
  "initial_prediction": { "suggested_classification": "FAMILY", "confidence": 0.71, "action": "ASK_MERCHANT", "classification_source": "RULE" },
  "classification_history": [
    { "ledger_entry_id": "LE-M001-000874", "entry_type": "PAYMENT_IN", "classification": "PENDING", "source": "RULE", "at": "2026-11-15T19:42:10+05:30" },
    { "ledger_entry_id": "LE-M001-000875", "entry_type": "RECLASSIFICATION", "classification": "FAMILY", "source": "MERCHANT_CONFIRMED", "at": "2026-11-15T19:43:02+05:30" }
  ],
  "refunded_paise": 0,
  "reversed": false
}
```

### GET `/merchants/{merchant_id}/payments`
Query: `start_date`, `end_date` (inclusive, default today–today), `classification` (`SALE|FAMILY|PENDING`), `limit` (default 200, max 1000), `offset`.
`200`
```json
{ "merchant_id": "M001", "count": 15, "items": [ { "transaction_id": "...", "timestamp": "...", "payer_name": "...", "amount_paise": 4000, "amount_display": "₹40", "current_classification": "SALE", "confidence": 0.98, "classification_source": "MODEL" } ] }
```
Sorted by `timestamp` ascending. In each item, `confidence` is the initial prediction's confidence (`null` for `MERCHANT_CONFIG`) and `classification_source` is the current source (e.g. `MERCHANT_CONFIRMED` after an answer).

### POST `/payments/{transaction_id}/refund`  (simulation, used in tests and history)
The merchant refunded part or all of a payment to the payer. Idempotent on `refund_id`.
```json
{ "refund_id": "RF-M001-000012", "amount_paise": 6000, "timestamp": "2026-11-14T10:05:00+05:30", "reason": "Returned tomatoes" }
```
`201`: `{ "refund_id": "...", "ledger_entry_id": "...", "remaining_refundable_paise": 0 }`.
`409 INVALID_STATE` if amount > remaining refundable, or payment reversed.

### POST `/payments/{transaction_id}/reversal`  (simulation)
The bank reversed the payment (failed/duplicate). Entire amount. Idempotent per transaction.
```json
{ "timestamp": "2026-11-14T12:00:00+05:30", "reason": "Bank reversal" }
```
`201`: `{ "transaction_id": "...", "ledger_entry_id": "...", "reversed": true }`.
`409 INVALID_STATE` (`details.reason = "HAS_REFUNDS"`) if the payment already has any refund. Rule: a payment is either refunded (partly or fully) or reversed, never both. Refund after reversal is also `409`.

---

## 4. Questions and confirmation

### GET `/merchants/{merchant_id}/questions`
Query: `status` (default `OPEN`), `date` (optional, IST date of the payment; the demo uses `date=2026-11-15`), `language` (default merchant's preferred). Sorted **newest first**. The seed history deliberately contains 3 older OPEN questions, so the UI must open questions by `question_id` (from `/demo/next-payment` or the list), never by position.
`200`
```json
{
  "merchant_id": "M001",
  "items": [
    {
      "question_id": "Q-M001-000057",
      "transaction_id": "TXN-M001-20261115-015",
      "payer_name": "Lakshmi R",
      "amount_paise": 200000,
      "amount_display": "₹2,000",
      "timestamp": "2026-11-15T19:42:10+05:30",
      "suggested_classification": "FAMILY",
      "confidence": 0.71,
      "question_text": "லக்ஷ்மி கிட்ட இருந்து 2,000 ரூபாய் வந்திருக்கு. இது கடை வியாபாரமா, வீட்டு பணமா?",
      "question_text_en": "₹2,000 received from Lakshmi R. Is this a shop sale or family money?",
      "question_audio_id": "AUD-3f9a1c0be27d4411",
      "status": "OPEN"
    }
  ]
}
```
`question_text` comes from the language template (not the LLM). `question_audio_id` may be `null` if TTS is not ready; frontend falls back to text.

### POST `/payments/{transaction_id}/confirm`
Stores the merchant's answer or correction. Creates a `RECLASSIFICATION` ledger entry (never edits the original) and a feedback record. **Same endpoint and same rules for tap and voice.**
```json
{ "merchant_id": "M001", "question_id": "Q-M001-000057", "confirmed_category": "FAMILY", "channel": "VOICE", "utterance_text": "veettu panam, eppavum", "remember_payer": true }
```
- `question_id`: required when answering a question; `null` for a correction from the ledger screen. The backend checks the question exists, belongs to this `transaction_id` and `merchant_id`; otherwise `409 INVALID_STATE` with `details.reason = "QUESTION_MISMATCH"`. This stops a voice answer from landing on a different open question.
- `remember_payer` (optional, default `false`). With `FAMILY` ("Always family"): adds the payer to the family payers. With `SALE` ("Remember as customer", offered by the UI after a SALE answer on a **P2P** payment): adds the payer to the customer payers; on a non-P2P payment → `422` (`details.field = "remember_payer"`). A payer is never in both lists: remembering in one removes them from the other in the same transaction, and `moved_from` says so. Affects future payments only.

`201`
```json
{
  "transaction_id": "TXN-M001-20261115-015",
  "previous_classification": "PENDING",
  "confirmed_category": "FAMILY",
  "ledger_entry_id": "LE-M001-000875",
  "feedback_id": "FB-M001-000031",
  "question_id": "Q-M001-000057",
  "question_status": "ANSWERED",
  "payer_memory": { "payer_id": "P90001", "confirmed_family": 1, "confirmed_sale": 0, "family_payer_configured": true, "customer_payer_configured": false },
  "moved_from": null,
  "idempotent_replay": false
}
```

**Correction workflow (one set of rules):**
| situation | result |
|---|---|
| Answer to an OPEN question | `201`, RECLASSIFICATION, feedback, question → ANSWERED |
| Same category as the current classification, and current source is already `MERCHANT_CONFIRMED` | `200`, `idempotent_replay: true`, nothing written (double tap, repeated voice "yes") |
| Different category from current (merchant changes his mind, or corrects an AUTO or MERCHANT_CONFIG decision) | `201`, new RECLASSIFICATION + new feedback. Only the latest answer per payment counts in payer memory |
| Same category as an AUTO decision (merchant "confirms" an auto one) | `201`, RECLASSIFICATION with source `MERCHANT_CONFIRMED`, feedback stored |
| Answering a question that is already ANSWERED, with a different category | treated as a correction (row 3) |
| Payment reversed | `409 INVALID_STATE` |
| Remember with `SALE` on a P2P payment | `201`, payer added to customer payers (`customer_payer_configured: true`). If they were a family payer: removed from that list, `"moved_from": "FAMILY"` |
| Remember with `FAMILY` for a configured customer | `201`, payer moved to family payers, `"moved_from": "CUSTOMER"` |
| Correcting a payment from a configured family payer to SALE | `201`; the payer stays configured; response includes `"suggest_unconfigure": true` so the UI can ask "Stop treating {name} as always family?" |

### POST `/classify/preview`
Runs the full decision procedure for a hypothetical payment **without writing anything**. Used on the Learning screen to show "what happens next time this person pays".
```json
{ "merchant_id": "M001", "payer_id": "P90001", "amount_paise": 200000, "payment_type": "P2P", "timestamp": "2026-11-15T20:30:00+05:30" }
```
`200`
```json
{ "suggested_classification": "FAMILY", "confidence": null, "confidence_kind": "NONE", "action": "AUTO_CLASSIFY", "classification_source": "MERCHANT_CONFIG", "reasons": ["Marked as family by merchant"], "written": false }
```
UI text for this case: "Next time: family, because you told Naanayam to remember (you can change this)". Never a percentage.
Configured customer: `SALE`, `AUTO_CLASSIFY`, `MERCHANT_CONFIG`, `confidence: null`, reason "Marked as customer by merchant" (fixture `classify_preview_customer.json`). Guardrails (DATA 5.6 rules 5d and 1b) return `ASK_MERCHANT`, source `RULE`, with the model's suggestion and confidence, first reason "Looks like a shop sale from a family payer" / "Looks like family money from a customer" (fixture `classify_preview_guardrail_ask.json`).

---

## 5. Expenses

### POST `/expenses`
Idempotent on `client_request_id`. The frontend creates one UUID **per confirmation-card draft**: retries and double taps of the same draft reuse it; if the merchant edits the amount, category or date on the card, the draft gets a **new** UUID. The backend revalidates amount (₹1 to ₹5,00,000), category, merchant and timestamp (not in the future, not more than 7 days back).
```json
{
  "client_request_id": "6f1c2a8e-1d7b-4c2e-9b9a-0c3d2e1f4a5b",
  "merchant_id": "M001",
  "amount_paise": 310000,
  "category": "STOCK_PURCHASE",
  "description": "Kaaikari, Koyambedu",
  "timestamp": "2026-11-15T05:40:00+05:30",
  "input_source": "VOICE",
  "language": "ta",
  "utterance_text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen",
  "voice_log_id": "VL-M001-000112"
}
```
`201`
```json
{
  "expense_id": "EXP-M001-000231",
  "ledger_entry_id": "LE-M001-000860",
  "amount_paise": 310000,
  "amount_display": "₹3,100",
  "category": "STOCK_PURCHASE",
  "status": "RECORDED",
  "idempotent_replay": false
}
```
`200` + `"idempotent_replay": true` on identical replay. `409 DUPLICATE_CONFLICT` if same `client_request_id` with different content.

### GET `/merchants/{merchant_id}/expenses`
Query: `start_date`, `end_date`, `category`, `include_voided` (default false).
`200`: `{ "merchant_id": "M001", "count": 1, "items": [ { "expense_id": "...", "timestamp": "...", "amount_paise": 310000, "amount_display": "₹3,100", "category": "STOCK_PURCHASE", "description": "...", "input_source": "VOICE", "voided": false, "ledger_entry_id": "..." } ] }`

### POST `/expenses/{expense_id}/void`
Expenses are never edited or deleted. To fix a mistake: void, then create a new one.
```json
{ "merchant_id": "M001", "reason": "Wrong amount" }
```
`201`: `{ "expense_id": "...", "void_ledger_entry_id": "...", "status": "VOIDED" }`. `409 INVALID_STATE` if already voided.

---

## 6. Voice

All voice endpoints live in the backend (Sarvam keys never reach the browser).

### POST `/voice/transcribe`  (multipart)
Fields: `audio` (file: webm/ogg/wav/mp3, ≤ 30 s), `language` (`ta|te`), `merchant_id`, optional `demo_key`.

Two separate paths:
- **Live mic (no `demo_key`)**: cache key = hash of the actual audio bytes + model + params. In `live`/`cache_first` an unseen recording is sent to Sarvam (`recognition_mode: LIVE`); the same bytes seen before return `CACHED_LIVE`. In `cache_only` an unseen recording → `503 CACHE_MISS` (the UI says "Can't reach Sarvam right now" and offers tap input). A live recording can **never** return a scripted transcript.
- **Recorded demo clip (`demo_key` set)**: only accepted if the uploaded bytes' sha256 equals the hash stored for that key in `cache/sarvam_demo/demo_clips.json`; otherwise `422 VALIDATION_ERROR` ("audio does not match demo clip"). Returns `recognition_mode: RECORDED_DEMO`. The UI shows the badge "Recorded demo clip".
`200`
```json
{
  "voice_log_id": "VL-M001-000112",
  "text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen",
  "language": "ta",
  "provider": "sarvam",
  "recognition_mode": "RECORDED_DEMO",
  "from_cache": true,
  "duration_ms": 3400
}
```
Errors: `422` (empty/too long audio), `503 SARVAM_UNAVAILABLE`, `503 CACHE_MISS`.

### POST `/voice/interpret`
Turns text into a structured intent. The LLM proposes; deterministic validation decides (see `docs/VOICE_AND_NOTICE.md`).
```json
{ "merchant_id": "M001", "language": "ta", "text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen", "voice_log_id": "VL-M001-000112", "open_question_id": null }
```
`200`
```json
{
  "intent": "LOG_EXPENSE",
  "entities": {
    "amount_paise": 310000,
    "amount_display": "₹3,100",
    "category": "STOCK_PURCHASE",
    "description": "Kaaikari, Koyambedu",
    "date": "2026-11-15",
    "confirmed_category": null
  },
  "needs_clarification": false,
  "clarification_text": null,
  "confirmation_text": "₹3,100 kaaikari selavu (Koyambedu). Sari-yaa?",
  "validation": { "amount_found_in_text": true, "category_valid": true },
  "from_cache": true
}
```
Per intent, `entities` uses:
- `LOG_EXPENSE`: `amount_paise`, `amount_display`, `category`, `description`, `date`
- `ASK_DAILY_PROFIT`: `date` (today, or yesterday for "nethu" / "ninna")
- `CONFIRM_TRANSACTION`: `confirmed_category` (`SALE|FAMILY`), `remember_payer` (bool), requires `open_question_id` in the request
- `UNKNOWN`: none; `needs_clarification: true` with a template `clarification_text`

If the amount cannot be validated against the transcript → `needs_clarification: true`, `clarification_text` asks for the amount again. The frontend must **not** call `/expenses` until `needs_clarification` is false **and** the merchant has confirmed (tap "Sari" or says yes).

### POST `/voice/answer`
Builds a spoken answer from backend numbers using the **fixed language template only** (no LLM for money). A slot check verifies each number sits in its own slot (sales in the sales slot, etc.) before TTS.
```json
{ "merchant_id": "M001", "language": "ta", "intent": "ASK_DAILY_PROFIT", "date": "2026-11-15" }
```
`200`
```json
{
  "text": "இன்னைக்கு கடை வியாபாரம் 4,820 ரூபாய். செலவு 3,100 ரூபாய். மீதம் 1,720 ரூபாய். வீட்டு பணம் 2,000 ரூபாய் இதுல சேர்க்கல.",
  "language": "ta",
  "facts": {
    "business_sales": { "amount_paise": 482000, "amount_display": "₹4,820" },
    "expenses": { "amount_paise": 310000, "amount_display": "₹3,100" },
    "profit": { "amount_paise": 172000, "amount_display": "₹1,720" },
    "family_transfers": { "amount_paise": 200000, "amount_display": "₹2,000" },
    "pending_count": 0
  },
  "number_check": { "passed": true, "slots": { "sales": 482000, "expenses": 310000, "profit": 172000, "family": 200000 } },
  "scope_note": "UPI payments only. Profit = business sales minus expenses you entered.",
  "audio_id": "AUD-91c2d0aa7e5b3f12",
  "from_cache": true
}
```
If `pending_count > 0`, the text must say how many payments are still unconfirmed. `number_check.slots` lists only the slots actually spoken (`loss` instead of `profit` on a loss day, `pending_count` when > 0). `audio_error` (additive): `null`, or the TTS error code (`CACHE_MISS`, `SARVAM_UNAVAILABLE`) when no audio could be made; the text and numbers are still returned and shown. Only today has a spoken template so far; another `date` → `422` until a template key exists. If the slot check fails (a template bug), return `500 INTERNAL_ERROR` and the UI shows the numbers without speech; never speak an unchecked number.

### POST `/voice/speak`
```json
{ "merchant_id": "M001", "language": "ta", "text": "₹3,100 kaaikari selavu save pannitten." }
```
`200`: `{ "audio_id": "AUD-...", "audio_url": "/api/audio/AUD-...", "from_cache": false }`
`503` → frontend shows the text only.

### GET `/audio/{audio_id}`
Returns the audio file (`audio/wav` or `audio/mpeg`). `404` if unknown.

---

## 7. Summary, ledger, provenance

### GET `/merchants/{merchant_id}/summary`
Query: `start_date`, `end_date` (default today), `include_sources` (default false).
`200`
```json
{
  "merchant_id": "M001",
  "period": { "start_date": "2026-11-15", "end_date": "2026-11-15" },
  "total_collections": { "amount_paise": 682000, "amount_display": "₹6,820" },
  "business_sales": { "amount_paise": 482000, "amount_display": "₹4,820" },
  "family_transfers": { "amount_paise": 200000, "amount_display": "₹2,000" },
  "pending": { "amount_paise": 0, "amount_display": "₹0", "count": 0 },
  "refunds": { "amount_paise": 0, "amount_display": "₹0" },
  "reversals": { "amount_paise": 0, "amount_display": "₹0" },
  "expenses": { "amount_paise": 310000, "amount_display": "₹3,100" },
  "profit": { "amount_paise": 172000, "amount_display": "₹1,720", "label": "Recorded profit" },
  "scope_note": "UPI payments only. Profit = business sales minus expenses you entered. Cash sales, unrecorded expenses and stock changes are not included.",
  "attribution_note": "Refunds and reversals are counted on the date of the original payment, so past days can change when a later refund happens.",
  "as_of": "2026-11-15T19:43:05+05:30",
  "reconciliation_ok": true,
  "sources": null
}
```
With `include_sources=true`, `sources` is:
```json
{ "business_sales": ["LE-M001-000861", "..."], "family_transfers": ["LE-M001-000875"], "expenses": ["LE-M001-000860"], "refunds": [], "reversals": [], "pending": [] }
```
`reconciliation_ok` = the identity in `docs/DATA_AND_LOGIC.md` 7.3 holds. If false, the frontend shows a red warning (this should never happen; it means a bug).

### GET `/merchants/{merchant_id}/ledger`
Query: `start_date`, `end_date`, `entry_type`, `classification`, `limit` (default 200), `offset`.
`200`
```json
{
  "merchant_id": "M001",
  "count": 17,
  "items": [
    {
      "ledger_entry_id": "LE-M001-000875",
      "seq": 875,
      "entry_type": "RECLASSIFICATION",
      "source_type": "PAYMENT",
      "source_id": "TXN-M001-20261115-015",
      "supersedes_entry_id": "LE-M001-000874",
      "amount_paise": 200000,
      "amount_display": "₹2,000",
      "classification": "FAMILY",
      "classification_source": "MERCHANT_CONFIRMED",
      "confidence": null,
      "effective_at": "2026-11-15T19:42:10+05:30",
      "created_at": "2026-11-15T19:43:02+05:30",
      "prev_hash": "9b1e...c04a",
      "hash": "4d7f...e912"
    }
  ]
}
```
`source_type`: `PAYMENT`, `EXPENSE`, `REFUND`, `REVERSAL`.

### GET `/ledger/{ledger_entry_id}`
`200`: one entry (same shape) plus `"source": { ...the payment or expense object... }`.

### GET `/merchants/{merchant_id}/ledger/verify`
`200`
```json
{ "merchant_id": "M001", "status": "VALID", "entries_checked": 875, "first_invalid_entry_id": null, "message": "All 875 entries verified. No changes detected." }
```
`status`: `VALID` or `TAMPERED`. When `TAMPERED`, `first_invalid_entry_id` and a message naming the problem (`hash_mismatch` or `prev_hash_mismatch`).

### POST `/demo/tamper`  (demo only, `ENABLE_DEMO_TOOLS=true`)
Directly edits one entry's amount in SQLite without updating hashes, so `/ledger/verify` can show detection live. Code lives in `backend/app/demo/tamper.py` and is never imported by any other module. `/health` reports `"tampered": true` and the UI shows a red banner until `/demo/reset`. `{ "merchant_id": "M001", "ledger_entry_id": "LE-M001-000861" }` → `200 { "tampered": true }`. `/demo/reset` undoes it.

---

## 8. Learning and evaluation

### GET `/merchants/{merchant_id}/learning`
`200`
```json
{
  "merchant_id": "M001",
  "corrections_total": 31,
  "known_payers": 412,
  "payers_with_memory": 9,
  "family_payers_configured": 1,
  "questions_asked": { "today": 1, "last_7_days": 6, "first_7_days": 23 },
  "auto_classified_today": 14,
  "recent_feedback": [ { "feedback_id": "FB-M001-000031", "payer_name": "Lakshmi R", "confirmed_category": "FAMILY", "at": "2026-11-15T19:43:02+05:30" } ]
}
```
All counts from the database. `first_7_days` = first 7 days of the merchant's history. Also `customer_payers_configured` and `payers`: both configured lists and the payers with answers, each `{ payer_id, payer_name, kind, source, relation_label, confirmed_family, confirmed_sale }` with `kind` = `FAMILY_INSTRUCTION` ("always family, your instruction"), `CUSTOMER_INSTRUCTION` ("always a customer, your instruction"), `MIXED` (rule 5a: always asked) or `MEMORY` (answers nudge the model), and `source` = `SETUP` / `CONFIRMATION` (how the instruction was given) or `ANSWERS`. Shown as activity; the Learning headline is the evaluation's weekly questions (C vs E).

### GET `/evaluation`
Returns the latest evaluation run file (`data/eval/latest.json`), produced by `python -m ml.evaluate`. Never hand-edited.
`200`
```json
{
  "run_id": "eval-2026-11-14-01",
  "created_at": "2026-11-14T15:10:00+05:30",
  "data_label": "Synthetic data (generator seed 42)",
  "model_version": "clf-2026-11-14-01",
  "threshold": 0.9,
  "split": { "train_merchants": 70, "test_merchants": 110, "test_period": "2026-10-16 to 2026-11-14", "test_transactions": 152189 },
  "baseline": { "precision_auto": 0.962, "coverage": 0.71, "questions_per_merchant_per_day": 6.1, "overall_accuracy": 0.991 },
  "with_feedback": { "precision_auto": 0.974, "coverage": 0.88, "questions_per_merchant_per_day": 2.3, "overall_accuracy": 0.993 },
  "questions_per_day_by_week": { "baseline": [6.3, 6.0, 6.2, 5.9], "with_feedback": [4.1, 2.6, 1.9, 1.7] },
  "pr_coverage_curve": [ { "threshold": 0.5, "precision_auto": 0.91, "coverage": 1.0 }, { "threshold": 0.9, "precision_auto": 0.962, "coverage": 0.71 } ],
  "confusion_matrix_auto": { "labels": ["SALE", "FAMILY"], "matrix": [[12000, 210], [190, 640]] },
  "calibration": { "ece": 0.021, "bins": [ { "p_mean": 0.55, "accuracy": 0.57, "count": 410 } ] },
  "merchant_answer_error_rate": 0.02
}
```
**The numbers above are placeholders to show the shape. Real values come only from the run.** The file also has `label_mix` (`count_share` and `value_share` of FAMILY, per split; see `docs/DATA_AND_LOGIC.md` 4.3) and a `conditions` object with all five evaluation conditions (A always-SALE, B naive rule, C model no feedback, D payer memory, E full system) and their metrics, per `docs/DATA_AND_LOGIC.md` 11.3–11.4. `baseline` = C, `with_feedback` = E. **Headline first:** the file has `headline` (for `always_sale` = A, `baseline` = C, `with_feedback` = E): `family_money_found` {count, of}, `income_wrongly_removed` {count, of, silent, merchant_answer_errors}, `questions_per_merchant_per_day`. The screen leads with these ("family money found X of N", "income wrongly removed Y of M", questions per merchant per day); precision_auto and precision by source are secondary and always shown next to the always-SALE baseline. The file also has `threshold_selection` (objective, constraints, chosen row, full calibration-set table) and `threshold_curve_calibration` (family recall and questions/day vs τ). The Learning screen fetches **both** endpoints: `/merchants/{id}/learning` for this merchant's activity (questions asked, corrections, payer memory), and `/evaluation` for model metrics (precision by source, config errors, conditions, curve). `/learning` never returns precision figures. The Learning screen must show `precision_auto_by_source` (MODEL, PAYER_MEMORY, MERCHANT_CONFIG) and `config_errors` next to any headline precision, never one combined figure alone. `overall_accuracy` counts ASK items as answered by the simulated merchant (with 2% simulated answer errors). Family-specific metrics inside `conditions` (`family_recall_final`, `silent_family_errors`, `silent_sale_errors`, `config_errors`) are objects with counts and denominators, e.g. `{ "count": 9, "of": 512, "rate": 0.0176 }`; the UI shows "9 of 512".

---

## 9. Tax summary, notices

### GET `/merchants/{merchant_id}/tax-summary`
Query: `start_date`, `end_date` (default: 1 Aug 2026 to today).
`200`
```json
{
  "merchant_id": "M001",
  "period": { "start_date": "2026-08-01", "end_date": "2026-11-15" },
  "business_category": "VEGETABLES",
  "gst_treatment": "EXEMPT_LIKELY",
  "gst_treatment_basis": "Merchant configured category VEGETABLES (fresh vegetables are generally GST-exempt). Not inferred from payments.",
  "ca_review_required": true,
  "total_collections": { "amount_paise": 0, "amount_display": "₹0" },
  "business_sales": { "amount_paise": 0, "amount_display": "₹0" },
  "family_transfers": { "amount_paise": 0, "amount_display": "₹0" },
  "pending": { "amount_paise": 0, "amount_display": "₹0", "count": 0 },
  "expenses_recorded": { "amount_paise": 0, "amount_display": "₹0", "count": 0 },
  "flags": ["CA_REVIEW_REQUIRED"]
}
```
(Amounts shown as 0 here only for shape.) For `MIXED_KIRANA`: `gst_treatment: "UNKNOWN"`, `flags: ["MIXED_CATEGORY_SPLIT_UNKNOWN", "CA_REVIEW_REQUIRED"]`. No estimated split figures are returned.

### POST `/notices/analyse`  (multipart)
Fields: `merchant_id`, `file` (png/jpg/pdf), optional `demo_key` (`"sample_notice_v1"` for the committed sample).
`201`
```json
{
  "notice_id": "NTC-M001-001",
  "merchant_id": "M001",
  "fields": {
    "notice_title":        { "value": "Notice regarding turnover based on UPI receipts", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.93 },
    "issuing_office":      { "value": "Office of the Assistant Commissioner (Sample)", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.9 },
    "reference_number":    { "value": "SAMPLE/2026/0417", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.95 },
    "period_start":        { "value": "2026-08-01", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.94 },
    "period_end":          { "value": "2026-10-31", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.94 },
    "amount_questioned_paise": { "value": 0, "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.92 },
    "response_deadline":   { "value": "2026-11-30", "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.9 },
    "documents_requested": { "value": ["Details of UPI receipts", "Nature of goods supplied"], "origin": "EXTRACTED_FROM_NOTICE", "confidence": 0.85 }
  },
  "explanation": { "language": "ta", "text": "(Tamil explanation, template-based, see VOICE_AND_NOTICE.md)", "audio_id": "AUD-..." },
  "missing_fields": [],
  "disclaimer": "Sample notice. Naanayam explains and organises records. It does not give legal advice or reply to notices. A CA must review.",
  "from_cache": true
}
```
Any field not found: `value: null`, `origin: "NOT_FOUND"`, listed in `missing_fields`.

### GET `/merchants/{merchant_id}/notices/{notice_id}/evidence`
Every figure below is `DERIVED_FROM_LEDGER` for the notice period.
```json
{
  "notice_id": "NTC-M001-001",
  "period": { "start_date": "2026-08-01", "end_date": "2026-10-31" },
  "amount_questioned": { "amount_paise": 0, "amount_display": "₹0", "origin": "EXTRACTED_FROM_NOTICE" },
  "ledger_view": {
    "total_collections": { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER" },
    "business_sales":    { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER", "entry_count": 0 },
    "family_transfers":  { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER", "entry_count": 0 },
    "refunds_and_reversals": { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER" },
    "unresolved":        { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER", "entry_count": 0 },
    "expenses_recorded": { "amount_paise": 0, "amount_display": "₹0", "origin": "DERIVED_FROM_LEDGER", "entry_count": 0 }
  },
  "difference_vs_notice": { "amount_paise": 0, "amount_display": "₹0", "explanation": "Notice amount minus ledger total collections for the same period" },
  "gst_treatment": "EXEMPT_LIKELY",
  "family_transfer_examples": [ { "transaction_id": "...", "date": "2026-09-03", "payer_name": "Karthik", "amount_display": "₹2,000", "confirmed_by": "MERCHANT_CONFIG" } ],
  "ca_review_warnings": [
    "GST treatment is based on the merchant's declared category, not on individual sales.",
    "Family transfer labels are the merchant's own confirmations.",
    "Cash sales and payments through other apps are not in this ledger."
  ],
  "ledger_verify_status": "VALID"
}
```
No figure is invented: if the ledger has no data for part of the period, return `0` and add a warning. If the amount questioned was not read: `amount_questioned.origin = "NOT_FOUND"`, `difference_vs_notice.amount_paise = null`, plus a warning. `family_transfer_examples` lists only merchant-labelled payments (`MERCHANT_CONFIG` / `MERCHANT_CONFIRMED`). The notice is read from the `notices` table: `analyse()` stores it with `app.notice.store.save_notice(...)`. If the notice period was not extracted → `422 VALIDATION_ERROR`. Bucket definitions: `docs/DATA_AND_LOGIC.md` 7.3 and 9.

---

## 10. Credit passport (show only)

### GET `/merchants/{merchant_id}/passport`
Query: `months` (default 3, max 3; uses complete calendar months before `DEMO_DATE`: Aug, Sep, Oct 2026).
`200`
```json
{
  "merchant_id": "M001",
  "months": [
    { "month": "2026-08", "raw_collections_display": "₹0", "family_transfers_display": "₹0", "refunds_reversals_display": "₹0", "business_sales_display": "₹0", "expenses_display": "₹0", "recorded_income_display": "₹0", "unresolved_count": 0 }
  ],
  "totals": { "raw_collections": {"amount_paise":0,"amount_display":"₹0"}, "recorded_business_income": {"amount_paise":0,"amount_display":"₹0"} },
  "share_of_collections_that_were_business_sales": 0.0,
  "ledger_verify_status": "VALID",
  "label": "Recorded business income summary. Not verified income. Not a credit decision.",
  "consent_note": "Shared only with the merchant's consent."
}
```
(Each month also returns `*_paise` integers alongside the display strings.)

---

## 11. Export

### GET `/merchants/{merchant_id}/export/csv?start_date=&end_date=`
`200 text/csv`, filename `naanayam_M001_<start>_<end>.csv`. Columns, in order:
`ledger_entry_id, seq, entry_type, effective_at, source_type, source_id, payer_or_description, amount_rupees, classification, classification_source, confidence, expense_category, supersedes_entry_id, hash`
`amount_rupees` is the only place rupees appear as a decimal (2 dp), for CA spreadsheets. Default period: 2026-08-01 to today (as the tax summary). Rows follow the `/summary` attribution: every ledger entry of a payment dated in the period (including its later reclassifications, refunds and reversal) and of an expense dated in the period (EXPENSE and EXPENSE_VOID), in `seq` order, so the file reconciles with `/summary`. First lines of the file are `#` comments: merchant, period, generated `as_of`, ledger verify status, the scope note and the attribution note from `/summary`.

### GET `/merchants/{merchant_id}/export/pdf?start_date=&end_date=`
`200 application/pdf`, 1–2 pages: header (merchant, period, generated at, ledger verify status), summary table (collections, business sales, family transfers, refunds/reversals, pending, expenses, recorded profit), scope note and attribution note, GST treatment + basis, unresolved items list, CA review warnings, footer "Generated by Naanayam from synthetic demo data". Amounts in the PDF read "Rs 4,820" (the standard PDF fonts have no ₹ glyph).

---

## 12. Frontend → endpoint map (Nagasai Sree)

| Screen | Calls |
|---|---|
| Soundbox simulator | `POST /demo/next-payment`, then `GET /audio/{question_audio_id}` if ASK |
| Questions | `GET /merchants/{id}/questions`, `POST /payments/{txn}/confirm` |
| Talk (mic) | `POST /voice/transcribe` → `POST /voice/interpret` → (confirm card) → `POST /expenses` or `POST /voice/answer` or `POST /payments/{txn}/confirm` → `GET /audio/{id}` |
| Today (proof of profit) | `GET /merchants/{id}/summary?include_sources=true` |
| Ledger | `GET /merchants/{id}/ledger`, `GET /ledger/{entry_id}`, `GET /merchants/{id}/ledger/verify` |
| Learning (for judges) | `GET /merchants/{id}/learning`, `GET /evaluation`, `POST /classify/preview` |
| Notice | `POST /notices/analyse`, `GET /merchants/{id}/notices/{nid}/evidence` |
| Passport | `GET /merchants/{id}/passport` |
| Export buttons | `GET .../export/csv`, `GET .../export/pdf` |
| Demo panel (hidden) | `POST /demo/reset`, `GET /demo/script`, `POST /demo/tamper`, `GET /health` |
