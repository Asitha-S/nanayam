# Naanayam: Voice and Notice Spec

> Owners: **M Charulatha** (Tamil voice, interpretation, template answers + slot check, notice reading and Tamil explanation), **Gummadi Nagasai Sree** (Telugu templates, Telugu test set, voice UI). Asitha owns the Sarvam client wrapper and cache.
> Read `PROJECT.md` and `contract/API_CONTRACT.md` sections 6 and 9 first.

> **All Tamil and Telugu text in this file was drafted by Claude and must be checked by Charulatha (Tamil) and Nagasai Sree (Telugu) before Friday night.** Fix anything that sounds unnatural for a Chennai vegetable seller or a Telugu fruit seller. Colloquial beats formal.

---

## 1. Principles

1. **The LLM proposes, code decides.** The LLM turns speech into a structured guess. Deterministic code validates amounts, categories and yes/no. Nothing is saved without the merchant confirming.
2. **The LLM never speaks money.** Financial answers come from fixed templates filled with backend facts and pass a positional slot check.
3. **A wrong save is worse than asking again.** The key voice metric is *wrong saves = 0*, not "accuracy".
4. **Every voice path has a tap path.** If voice fails at any step, the same action is possible by tapping.
5. **The demo never depends on the network.** Every scripted call is cached in `cache/sarvam_demo/`.

---

## 2. Sarvam services used

| Use | Sarvam service | Where |
|---|---|---|
| Speech to text (Tamil, Telugu, code-mixed) | Speech-to-text (Saarika / Saaras family) | `/voice/transcribe` |
| Intent + entity extraction | Sarvam chat LLM | `/voice/interpret` |
| Text to speech | Bulbul TTS | `/voice/speak`, question audio, answers |
| Reading the notice image/PDF | Sarvam Vision / document intelligence | `/notices/analyse` |
| Transliteration for display (optional) | Transliterate API | romanized names → Tamil script |

**Friday task (Charulatha):** open docs.sarvam.ai, confirm the current model IDs, request fields, language codes (`ta-IN`, `te-IN`) and TTS speaker names. Put them in `backend/app/sarvam/models.py` as constants. Do not hard-code model names anywhere else.

Pick one Tamil TTS voice and one Telugu TTS voice that sound like a friendly shop helper, and use them everywhere.

---

## 3. Sarvam client and cache (Asitha writes, everyone uses)

`backend/app/sarvam/client.py` exposes four functions: `stt(audio_bytes, lang, demo_key=None)`, `chat(messages, schema=None)`, `tts(text, lang)`, `vision(file_bytes, demo_key=None)`.

**Cache key** = sha256 of `service + model_id + canonical JSON of parameters + sha256(input bytes or text)`. Always. There is no key that ignores the input.

**Recorded demo clips** are different from cache lookups: `cache/sarvam_demo/demo_clips.json` maps each `demo_key` to the sha256 of its committed WAV file. `/voice/transcribe` with a `demo_key` first checks the uploaded bytes match that hash (else 422), then uses the normal content-hash cache. So a demo key can only ever return the transcript of the exact clip it names, and the response says `recognition_mode: RECORDED_DEMO`.

| path | when | label on screen |
|---|---|---|
| Recorded demo clip | "Play demo voice" button | "Recorded demo clip" |
| Live mic, Sarvam reachable | judge or us speaking | "Live" |
| Live mic, same audio as before | rare (identical bytes) | "Live (cached)" |
| Live mic, no network, `cache_only` | | "Can't reach Sarvam right now" + tap input |

**Storage:** `cache/sarvam_demo/{key}.json` (+ `{key}.wav` for TTS) when `SARVAM_CACHE_DIR=demo`; `cache/sarvam_dev/` otherwise.

| DEMO_MODE | behaviour |
|---|---|
| `cache_only` | Return cached response. On miss: raise `CACHE_MISS` (503). Never calls Sarvam. **Used on stage.** |
| `cache_first` | Return cached; on miss call Sarvam, store, return. **Used in development, and on stage if the venue Wi-Fi works, so a judge can try an unscripted sentence.** |
| `live` | Always call Sarvam, store result. Used to refresh the demo cache. |

- Timeout 8 s for STT/LLM, 10 s for TTS/vision. One retry on timeout or 5xx, then `SARVAM_UNAVAILABLE`.
- Every live call is logged to `logs/sarvam_calls.jsonl` (time, service, latency, ok, person). Check credit use on the Sarvam dashboard Friday night and Saturday evening. We have 500 credits each; develop in `cache_first` so repeated runs cost nothing.
- **Script `python -m backend.app.sarvam.warm_demo_cache`** runs every scripted demo call in `live` mode and writes `cache/sarvam_demo/`. Run it after any template or prompt change, then commit the cache.

---

## 4. Voice flows (Tamil shown; Telugu identical with te templates)

### 4.1 Shared mic flow (frontend, Nagasai Sree)

```
[Mic tap] → record (max 15 s; Stop tap, or auto-stop after 2.5 s silence measured against the room's noise floor, never before 3 s)
   → POST /voice/transcribe  → show transcript in small text ("Naan kettadhu: ...")
   → POST /voice/interpret   (with open_question_id if a question card is open)
   → branch on intent
```

States shown on screen: `Listening…` → `Understanding…` → confirmation card / answer / clarification. Each state has a Tamil label from templates.

### 4.1a Card binding rules (apply to every flow)
1. Every card has an identity created when it is shown: an expense card has a `draft_id` (UUID, also used as `client_request_id`); a question card carries its `question_id` + `transaction_id`. A voice answer is sent with the identity of the card **currently on screen**, never looked up afterwards.
2. Only one card is active at a time. Opening a new card (new payment question, new expense) closes the previous one; a late response for a closed card is discarded by the frontend.
3. Retrying a failed save reuses the same identity. Editing amount, category or date on an expense card creates a new `draft_id`.
4. Switching merchant (demo panel) clears all cards and in-flight requests.
5. The backend revalidates everything (amount range, enums, merchant, question belongs to transaction); the frontend's checks are only for speed.

### 4.2 Flow A: Log expense

1. Murugan: "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen."
2. `/voice/interpret` → `LOG_EXPENSE`, amount 310000, `STOCK_PURCHASE`, description "Kaaikari, Koyambedu".
3. **Confirmation card** (big amount, category in Tamil, description, date) + TTS of `expense_confirm`:
   "₹3,100 சரக்கு செலவு (காய்கறி, கோயம்பேடு). சரியா?"
4. Murugan says "சரி" / "ஆமா" or taps **சரி** → frontend calls `POST /expenses` with `client_request_id` = the card's `draft_id` (so double taps or a retry never create two expenses; an edited card gets a new id).
5. TTS `expense_saved`: "₹3,100 செலவு சேமிச்சுட்டேன்." Ledger list updates.
6. If he says "இல்ல" / taps **மாற்று**: card becomes editable (amount field, category chips). If he taps **ரத்து**: nothing saved, voice_log outcome `CANCELLED`.

Edge rules:
- Amount > ₹50,000 → card shows a yellow "பெரிய தொகை" line and requires a tap (voice "sari" alone is not enough).
- Amount missing or not validated → `clarify_amount` ("எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க."). After 2 failed tries → open the manual form with whatever was understood pre-filled.
- Category unclear → default `OTHER` and the card shows category chips to tap. Never block on category.
- "Nethu" (yesterday) → date = DEMO_DATE − 1; card shows the date clearly.

### 4.3 Flow B: Daily profit

1. Murugan: "இன்னைக்கு எவ்வளவு லாபம்?" / "Innaikku evvalavu meedham?"
2. `/voice/interpret` → `ASK_DAILY_PROFIT`, date today.
3. `POST /voice/answer` → backend gets the summary, fills the template, runs the slot check, returns text + audio.
4. Screen shows the Today card with the same four numbers, highlighted as they are spoken. **Spoken numbers and screen numbers come from the same `facts` object.**

### 4.4 Flow C: Answer a payment question

1. Soundbox simulator: payment 15 arrives (Lakshmi ₹2,000, ASK). Question card appears and plays `question_payment`:
   "லக்ஷ்மி கிட்ட இருந்து ₹2,000 வந்திருக்கு. இது கடை வியாபாரமா, வீட்டு பணமா?"
2. Murugan: "வீட்டு பணம், அக்கா அனுப்பினாங்க." → `/voice/interpret` with `open_question_id` → `CONFIRM_TRANSACTION`, `FAMILY`, `remember_payer: false`.
3. Because it is FAMILY and the payer is not configured, play `remember_question`: "இனிமே லக்ஷ்மி அனுப்புறது எல்லாம் வீட்டு பணமா?" with two buttons **ஆமா, எப்பவும்** / **இந்த தடவை மட்டும்**.
4. "ஆமா" → `POST /payments/{txn}/confirm` with the card's `question_id`, `FAMILY`, `remember_payer: true`, `channel: VOICE`.
5. TTS `confirm_family_remembered`: "சரி. இனிமே லக்ஷ்மி பணம் வீட்டு பணமா எடுத்துக்கறேன். கடை கணக்குல சேர்க்க மாட்டேன்."
6. Tap path: the question card always has **கடை வியாபாரம்** / **வீட்டு பணம்** buttons.

If he answers "kadai" → SALE, no remember question.
If the utterance is neither (e.g. "theriyala") → `clarify_category` and keep the card open. The payment stays PENDING; that is fine.

### 4.5 Unknown intent
`not_understood`: "புரியல. செலவு சொல்லுங்க, இல்லன்னா இன்னைக்கு லாபம் கேளுங்க." Plus two big buttons: **செலவு சேர்** / **இன்னைக்கு லாபம்**.

---

## 5. Interpretation (`backend/app/voice/interpret.py`, Charulatha)

### 5.1 LLM call
- Temperature 0. System prompt (English instructions, Tamil/Telugu examples) asks for **only** this JSON:

```json
{
  "intent": "LOG_EXPENSE | ASK_DAILY_PROFIT | CONFIRM_TRANSACTION | UNKNOWN",
  "amount_rupees": 3100,
  "amount_text_span": "3,100",
  "category": "STOCK_PURCHASE | TRANSPORT | PACKAGING | RENT | WAGES | UTILITIES | OTHER | null",
  "description": "Kaaikari, Koyambedu",
  "day": "today | yesterday | null",
  "confirmed_category": "SALE | FAMILY | null",
  "remember_payer": false
}
```
- `amount_text_span` must be copied exactly from the transcript (the words or digits that say the amount).
- 8–10 few-shot examples from `data/voice_tests/ta_dev.jsonl` (dev split only, never the test items).
- Context passed: whether a question is open (and its payer/amount), so "veettu panam" is read as a confirmation.

### 5.2 Deterministic validation (always runs)

| check | rule | on failure |
|---|---|---|
| JSON parses, intent in enum | | rule-based fallback interpreter (5.3) |
| Amount span present | `amount_text_span` is a substring of the transcript (case/space-insensitive) | `needs_clarification` (amount) |
| Amount parses | `parse_amount(span)` gives an integer | `needs_clarification` |
| Amount agrees | `parse_amount(span) == amount_rupees` | `needs_clarification` |
| Range | ₹1 ≤ amount ≤ ₹5,00,000 | `needs_clarification` |
| Category valid | in enum, else `OTHER` | none (chips) |
| Confirmation | `confirmed_category` agrees with keyword match (5.4) if keywords present | `clarify_category` |
| CONFIRM without open question | | treat as `UNKNOWN` |

`parse_amount` handles: digits with/without commas ("3,100", "3100", "3 100"); "k" ("3k"); English words ("three thousand one hundred"); Tamil words (நூறு/நூத்தி 100, இருநூறு…தொள்ளாயிரம், ஆயிரம்/ஆயிரத்து 1000, லட்சம்); Telugu words (వంద 100, వెయ్యి/వేల 1000, లక్ష); romanized forms ("aayiram", "ayirathu", "nooru", "veyyi", "vanda"). Scope: 1 to 5,00,000. Unit tests for every form in the test set.

### 5.3 Rule-based fallback interpreter (when the LLM is down or returns junk)
- Amount: first span `parse_amount` can parse.
- Intent: profit keywords (லாபம், மீதம், கணக்கு, labham, meedham, lābhaṁ / లాభం) → `ASK_DAILY_PROFIT`; expense keywords (வாங்கி/வாங்கினேன், செலவு, kharchu/ఖర్చు, konnanu/కొన్నాను) + amount → `LOG_EXPENSE`; open question + category keyword → `CONFIRM_TRANSACTION`; else `UNKNOWN`.
- Category: keyword table 5.4.
- The fallback is also used to cross-check the LLM in tests.

### 5.4 Keyword tables (`voice/keywords.py`; Tamil by Charulatha, Telugu by Nagasai Sree)

| target | Tamil (script / romanized) | Telugu |
|---|---|---|
| STOCK_PURCHASE | காய்கறி, சரக்கு, வாங்கி, கோயம்பேடு / kaaikari, sarakku, vaangi, Koyambedu | కూరగాయలు, పండ్లు, సరుకు, కొన్నాను / kooragayalu, pandlu, konnanu |
| TRANSPORT | வண்டி, ஆட்டோ, லாரி / vandi, auto, lorry | ఆటో, లారీ, బండి |
| PACKAGING | கவர், பை / cover, pai | కవర్, సంచి |
| RENT | வாடகை / vaadagai | అద్దె / adde |
| WAGES | கூலி, சம்பளம் / kooli, sambalam | కూలి, జీతం |
| UTILITIES | கரண்ட், தண்ணி, EB | కరెంట్, నీళ్లు |
| FAMILY (answer) | வீட்டு, வீடு, குடும்ப, அக்கா, அண்ணன், தம்பி, அம்மா, அப்பா / veettu, akka, thambi | ఇంటి, ఇల్లు, కుటుంబం, అక్క, అన్న, తమ్ముడు, అమ్మ |
| SALE (answer) | கடை, வியாபாரம், விற்பனை, கஸ்டமர் / kadai, vyaabaaram, customer | షాప్, కొట్టు, అమ్మకం, వ్యాపారం, కస్టమర్ |
| YES | ஆமா, ஆம், சரி, ஓகே, கரெக்ட் / aamaa, sari, ok | అవును, సరే, ఓకే |
| NO | இல்ல, வேண்டாம், தப்பு / illa, vendaam | కాదు, వద్దు, తప్పు |
| REMEMBER | எப்பவும், இனிமே, எல்லாமே / eppavum, inime | ఎప్పుడూ, ఇకపై, అన్నీ |
| YESTERDAY | நேத்து / nethu | నిన్న / ninna |

---

## 6. Answer composition and slot check (`voice/answer.py`, Charulatha)

### 6.1 Facts
`/voice/answer` gets `facts` from the finance layer (the same function behind `/summary`). Amounts are formatted with `money.display` and then turned into speech form `"4,820 ரூபாய்"` / `"4,820 రూపాయలు"`.

### 6.2 Composition: templates only for money
Financial answers (daily profit, notice explanation figures, confirmation of saved amounts) are built **only** from `templates/{lang}.json`. No LLM rephrasing. Reason: a set-based check cannot catch an LLM that swaps sales and expenses while keeping the same numbers, and the gain in naturalness is small. Sarvam's LLM is still used where it adds real value: understanding what the merchant said (section 5) and reading the notice (section 11).

### 6.3 Slot check (guard against template bugs)
The composer fills named slots and records which value went into which slot. Before TTS:
```
for each slot in the template (sales, expenses, profit, family, loss, pending_count, dates):
    the text produced for that slot == money.speech(facts[slot])     # positional, not a set
the full text contains no digit groups other than the slot values
```
Fail → do not speak; return 500 and show numbers on screen. Unit tests: every template key in ta.json and te.json with sample facts; a deliberately swapped template fails.

### 6.4 TTS of numbers
Test on Friday how Bulbul reads "4,820 ரூபாய்". If it reads well, send as is. If not, convert digits to Tamil/Telugu words **only in the TTS input** with a deterministic function (`num_to_words_ta`, `num_to_words_te`); the displayed text and the slot check always use digits.

---

## 7. Templates

`backend/app/voice/templates/ta.json` (Charulatha) and `te.json` (Nagasai Sree). Placeholders in `{}`. Amount placeholders receive "4,820 ரூபாய்" style strings.

| key | Tamil draft | Telugu draft |
|---|---|---|
| question_payment | {payer_name} கிட்ட இருந்து {amount} வந்திருக்கு. இது கடை வியாபாரமா, வீட்டு பணமா? | {payer_name} నుండి {amount} వచ్చింది. ఇది షాప్ అమ్మకమా, ఇంటి డబ్బా? |
| remember_question | இனிமே {payer_name} அனுப்புறது எல்லாம் வீட்டு பணமா? | ఇకపై {payer_name} పంపేది అంతా ఇంటి డబ్బేనా? |
| confirm_family | சரி, இதை வீட்டு பணமா வச்சுட்டேன். கடை கணக்குல சேர்க்கல. | సరే, ఇది ఇంటి డబ్బుగా పెట్టాను. షాప్ లెక్కలో కలపలేదు. |
| confirm_family_remembered | சரி. இனிமே {payer_name} பணம் வீட்டு பணமா எடுத்துக்கறேன். கடை கணக்குல சேர்க்க மாட்டேன். | సరే. ఇకపై {payer_name} డబ్బు ఇంటి డబ్బుగా తీసుకుంటాను. షాప్ లెక్కలో కలపను. |
| confirm_sale | சரி, இதை கடை வியாபாரமா சேர்த்துட்டேன். | సరే, ఇది షాప్ అమ్మకంగా కలిపాను. |
| expense_confirm | {amount} {category} செலவு ({description}). சரியா? | {amount} {category} ఖర్చు ({description}). సరేనా? |
| expense_saved | {amount} செலவு சேமிச்சுட்டேன். | {amount} ఖర్చు సేవ్ చేశాను. |
| expense_large_warning | பெரிய தொகை. திரையில சரி-ன்னு தட்டுங்க. | పెద్ద మొత్తం. స్క్రీన్ మీద సరే నొక్కండి. |
| profit_answer | இன்னைக்கு கடை வியாபாரம் {sales}. செலவு {expenses}. மீதம் {profit}. | ఈరోజు షాప్ అమ్మకాలు {sales}. ఖర్చు {expenses}. లాభం {profit}. |
| profit_answer_loss | இன்னைக்கு கடை வியாபாரம் {sales}. செலவு {expenses}. இதுவரைக்கும் நஷ்டம் {loss}. | ఈరోజు అమ్మకాలు {sales}. ఖర్చు {expenses}. ఇప్పటివరకు నష్టం {loss}. |
| profit_family_suffix | வீட்டு பணம் {family} இதுல சேர்க்கல. | ఇంటి డబ్బు {family} ఇందులో కలపలేదు. |
| profit_pending_suffix | இன்னும் {pending_count} பணம் கடையா வீடா-ன்னு சொல்லல. | ఇంకా {pending_count} చెల్లింపులు నిర్ధారించలేదు. |
| profit_upi_only | (screen only) UPI பணம் மட்டும். கையில வாங்கின காசு இதுல இல்ல. | (screen only) UPI మాత్రమే. నగదు ఇందులో లేదు. |
| clarify_amount | எவ்வளவு ரூபாய்னு இன்னொரு தடவை சொல்லுங்க. | ఎంత రూపాయలో మళ్ళీ ఒకసారి చెప్పండి. |
| clarify_category | கடை வியாபாரமா, வீட்டு பணமா? கீழ தட்டுங்க. | షాప్ అమ్మకమా, ఇంటి డబ్బా? కింద నొక్కండి. |
| not_understood | புரியல. செலவு சொல்லுங்க, இல்லன்னா இன்னைக்கு லாபம் கேளுங்க. | అర్థం కాలేదు. ఖర్చు చెప్పండి, లేదా ఈరోజు లాభం అడగండి. |
| no_speech | கேக்கல. இன்னொரு தடவை சொல்லுங்க. | వినిపించలేదు. మళ్ళీ చెప్పండి. |
| offline | இப்போ இணைப்பு இல்ல. திரையில தட்டி சேர்க்கலாம். | ఇప్పుడు నెట్ లేదు. స్క్రీన్ మీద నొక్కి చేర్చవచ్చు. |
| saved_generic | சேமிச்சுட்டேன். | సేవ్ చేశాను. |

Category words: `category_names` map in each file (ta: STOCK_PURCHASE "சரக்கு", TRANSPORT "வண்டி", PACKAGING "கவர்", RENT "வாடகை", WAGES "கூலி", UTILITIES "கரண்ட்/தண்ணி", OTHER "மற்ற"; te: "సరుకు", "బండి", "కవర్", "అద్దె", "కూలి", "కరెంట్/నీళ్లు", "ఇతర").

UI labels (buttons, state labels) also live in the same files under `ui.*` so the frontend has one source.

Payer names: display as UPI gives them; for TTS, a small `payer_name_spoken` map in demo data (Lakshmi → லக்ஷ்மி, Srinivas → శ్రీనివాస్).

---

## 8. Failure handling (complete table)

| failure | what the merchant sees/hears | system |
|---|---|---|
| Mic permission denied | Text box "Type here" + buttons | voice_log not created |
| Silence / empty transcript | `no_speech` | voice_log FAILED |
| Recording > 15 s | auto-stop, process what was recorded | |
| STT timeout / 503 | `offline` + tap buttons | voice_log FAILED |
| `CACHE_MISS` on stage | same as offline (should never happen; rehearse) | logged loudly |
| LLM down / bad JSON | none visible; fallback interpreter used | `from_cache`/fallback flag logged |
| Amount not validated | `clarify_amount`; after 2 tries manual form pre-filled | CLARIFY |
| Category unknown | card with chips, default OTHER | |
| Merchant says "no" at card | editable card | |
| Cancel | nothing saved | CANCELLED |
| Save fails (5xx/network) | "Retry" button; retry uses the same `client_request_id` | idempotent |
| Double tap Save | one expense | idempotent |
| TTS fails | text shown, no audio | |
| Slot check fails (template bug) | numbers on screen, no speech | 500 logged; fix the template |
| Confirm on reversed payment | "இந்த பணம் திரும்ப போயிடுச்சு" (payment reversed) | 409 handled |
| Very large amount | `expense_large_warning`, tap required | |

---

## 9. Voice test sets

Files: `data/voice_tests/ta_dev.jsonl` (10, for prompts), `ta.jsonl` (30, test), `te_dev.jsonl` (6), `te.jsonl` (20). Audio in `data/voice_tests/audio/{lang}/`.

Line format:
```json
{"id":"ta-017","audio":"audio/ta/ta-017.wav","speaker":"S2","noise":"street","context_open_question":null,
 "expected_intent":"LOG_EXPENSE","expected_amount_paise":310000,"expected_category":"STOCK_PURCHASE",
 "expected_confirmed_category":null,"notes":"code-mixed, amount in digits"}
```

Composition of `ta.jsonl` (30): 12 expenses (digits, Tamil number words, English words, "3k", with/without place names), 8 profit questions (incl. "nethu"), 6 confirmations (4 family, 2 sale, 2 with "eppavum"), 4 tricky (noise, half sentence, unrelated, two amounts). At least 3 speakers (team + friends/family), at least 6 recorded with street/kitchen background noise. Telugu (20): 8 expenses, 6 profit, 4 confirmations, 2 tricky.

`python -m backend.app.voice.eval_voice --lang ta` reports, per item and overall:

| metric | target |
|---|---|
| **wrong_saves** (would save a wrong amount or category after the merchant says yes to a card showing it) | **0** |
| amount exact match or clarification asked | 100% |
| amount exact match without clarification | report (aim ≥ 80%) |
| intent accuracy | report (aim ≥ 90%) |
| confirmation category accuracy | report |
| STT latency p50 / p95 (live run) | report |

Note: wrong_saves counts cases where the card would show a wrong amount. Because the merchant confirms the card, a wrong card is still not a wrong save in real life, but we count it strictly. Results go in `data/voice_tests/results_{lang}.json` and onto the Learning screen as "Voice test: N Tamil recordings, amount correct or asked again in N/N".

---

## 10. Demo audio

Folder `assets/demo_audio/ta/` (Charulatha) and `te/` (Nagasai Sree). Record in a quiet room, phone mic, 16 kHz mono WAV:

| file | content |
|---|---|
| ta/expense_koyambedu.wav | "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen" |
| ta/confirm_yes.wav | "சரி" |
| ta/answer_family.wav | "வீட்டு பணம், அக்கா அனுப்பினாங்க" |
| ta/remember_yes.wav | "ஆமா, எப்பவும்" |
| ta/ask_profit.wav | "இன்னைக்கு எவ்வளவு லாபம்?" |
| te/expense_koyambedu.wav | "Koyambedu lo 4,200 rupayalaku pandlu konnanu" |
| te/answer_family.wav | "ఇంటి డబ్బు, తమ్ముడు పంపాడు" (or as appropriate for brother) |
| te/ask_profit.wav | "ఈరోజు లాభం ఎంత?" |

Each has a `demo_key` = its path under `assets/demo_audio/` without extension, including the language folder (`ta/expense_koyambedu`, `te/expense_koyambedu`), because ta/ and te/ share file names. Its sha256 goes into `demo_clips.json`; run `python -m backend.app.sarvam.register_demo_clips` from the repo root after recording. Playing one shows the "Recorded demo clip" badge. On stage: default to the recorded clips (Wi-Fi independent) and say so plainly: "this is a clip we recorded; you can also try the mic." If Wi-Fi works, keep `DEMO_MODE=cache_first` so a judge's unscripted sentence is genuinely transcribed. Rehearse the live mic with a stranger's voice on Saturday.

---

## 11. Notice mode (P3)

### 11.1 Scope
- **One** predefined sample notice, committed at `assets/notice/sample_notice.png` (+ PDF). Clearly watermarked "SAMPLE FOR DEMONSTRATION. NOT A REAL NOTICE."
- Naanayam reads it, explains it in Tamil, and builds an evidence summary from the ledger for a CA.
- It does **not** give legal advice, does not say whether tax is due, does not draft a reply.

### 11.2 Sample notice content (Charulatha creates; numbers from Asitha)
| field | value |
|---|---|
| Title | Intimation regarding receipts through UPI (SAMPLE) |
| Issued by | Office of the Assistant Commissioner, (Sample) Division, Chennai |
| Reference | SAMPLE/2026/0417 |
| Date of issue | 05-11-2026 |
| Addressed to | Murugan, Murugan Kaaikari Kadai, Chennai |
| Body | Receipts of ₹{amount} through UPI were observed in your account for 01-08-2026 to 31-10-2026. Explain the nature of these receipts and the goods supplied, and whether registration is required. |
| Documents requested | Details of UPI receipts; nature of goods supplied |
| Reply by | 30-11-2026 |

`{amount}` = M001 gross UPI receipts for the period, from `data/demo/notice_numbers.json` (Asitha publishes Friday). Format like a government letter (plain, typed, a seal-like box marked SAMPLE). Do not copy any real department's logo or emblem.

### 11.3 Extraction
1. `vision(file, demo_key="sample_notice_v1")` → OCR text (cached). The demo key is bound to the committed image by sha256, like the demo clips: after committing `assets/notice/sample_notice.png`, run `python -m backend.app.sarvam.register_demo_clips` (it registers `sample_notice_v1` in `cache/sarvam_demo/demo_clips.json`); any other file sent with that key is rejected with 422 (`app/notice/sample.py`, `check_sample_file`).
2. LLM extracts JSON with fields: `notice_title, issuing_office, reference_number, issue_date, period_start, period_end, amount_questioned_rupees, response_deadline, documents_requested[]`, each with an `evidence_span` copied from the OCR text.
3. Deterministic validation per field:
   - span must be found in OCR text, else `NOT_FOUND`;
   - dates parse (DD-MM-YYYY or DD/MM/YYYY) to ISO; amount parses to paise;
   - `period_start < period_end`; `response_deadline > issue_date`.
4. **Field confidence (deterministic, not LLM-reported):** 0.95 = span found verbatim and parsed cleanly; 0.80 = found after whitespace/case normalisation; otherwise `NOT_FOUND` with `value: null`.
5. Every field is shown on screen with a badge: **From notice** (`EXTRACTED_FROM_NOTICE`) or **From your ledger** (`DERIVED_FROM_LEDGER`) or **Not found**.

### 11.4 Tamil explanation (template; slot-checked)
```
இது ஒரு மாதிரி நோட்டீஸ். {office} அனுப்பியிருக்காங்க.
{period_start} முதல் {period_end} வரை உங்க UPI-ல வந்த {amount} பத்தி கேக்கறாங்க.
{deadline} க்குள்ள பதில் தரணும்.
உங்க கணக்குப்படி இந்த காலத்துல கடை வியாபாரம் {sales}, வீட்டு பணம் {family}.
இன்னும் {pending_count} பணம் உறுதி பண்ணல.
இந்த சுருக்கத்தை உங்க ஆடிட்டர் கிட்ட காட்டுங்க. நாணயம் சட்ட ஆலோசனை தராது.
```
Dates spoken as "ஆகஸ்ட் 1" style. Numbers from evidence (ledger) and extraction (notice) only; the slot check covers dates too. The explanation is only generated if all required fields were extracted; otherwise the screen shows the extraction error.

### 11.5 Notice screen (Nagasai Sree)
Left: notice image. Right: extracted fields with badges → "Your ledger for this period" table (collections, business sales, family, refunds/reversals, unresolved, expenses) each with a link to the filtered ledger → family examples → warnings → "Download CA pack" (PDF + CSV) → play Tamil explanation. Footer: disclaimer from the API, always visible.

---

## 12. Checklist by owner

**Charulatha (Tamil + notice)**
- [ ] Fri: confirm Sarvam model IDs/params; test STT on 5 Tamil clips; pick TTS voice; test number reading.
- [ ] Fri: review and fix every Tamil string in section 7 and 5.4.
- [ ] Fri: create sample notice image once Asitha posts the amount.
- [ ] Sat AM: `interpret.py` (LLM + validation + fallback), `parse_amount` with tests.
- [ ] Sat AM: `answer.py` (templates + slot check) with tests.
- [ ] Sat PM: notice extraction + Tamil explanation.
- [ ] Sat PM: record `ta.jsonl` test set + demo audio; run `eval_voice`; warm demo cache.
- [ ] Sun AM: fix failures from the test set; final cache warm; commit cache.

**Nagasai Sree (Telugu + UI)**
- [ ] Fri: review Telugu strings; record Telugu demo audio.
- [ ] Sat: mic component, confirmation card, question card, remember prompt, all states in 8.
- [ ] Sat PM: `te.json`, `te.jsonl` test set, run `eval_voice --lang te`.
