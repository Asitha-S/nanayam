# Shared fixtures

Example responses for every endpoint, used by:
- the backend stubs (Friday night) until real logic replaces them,
- the frontend in `VITE_API_BASE=fixtures` mode,
- voice and notice work before the backend is finished.

## Two kinds of fixture

**Exact (demo day, from `docs/DATA_AND_LOGIC.md` §3).** Amounts, payers, times and outcomes are the real expected values. The real backend must produce the same numbers. IDs and seq numbers are illustrative; the real ones depend on the seeded history.
`demo_*`, `payments_*`, `payment_get_015`, `questions_M001_open_2026-11-15`, `confirm_*`, `classify_preview_*`, `expenses_*`, `expense_void`, `voice_*`, `summary_M001_*`, `ledger_M001_2026-11-15` (17 entries with a real hash chain), `ledger_entry_detail`, `ledger_verify_*`, `error_*`, `merchants`, `merchant_M001`, `health`.

**Placeholder (depend on generated history or the evaluation run).** Right shape, invented numbers. **Never show these numbers in the pitch or a screenshot.** They are replaced by real API output after Saturday's seeding and evaluation.
`evaluation` (labelled "PLACEHOLDER NUMBERS" in `data_label`; its `split` and `label_mix` already use the generator's 70 train+calibration / 110 test merchants, M101–M280, and the seed-42 label mix, but every metric is still a placeholder), `learning_M001`, `tax_summary_*`, `notice_analyse`, `notice_evidence`, `passport_M001`, `questions_M001_open_all` (the 3 older open questions), `refund`, `reversal`.

## Customer memory and guardrails (2026-11-14, see CHANGES.md)
- `confirm_015.json` now has `"moved_from"` (`null` | `"FAMILY"` | `"CUSTOMER"`) and `payer_memory.customer_payer_configured`.
- `confirm_sale_remember_customer.json`: SALE answer on a P2P payment with `remember_payer: true` ("Remember as customer"). Offer that button only after a SALE answer on a P2P payment.
- `classify_preview_customer.json`: a remembered customer, shown as "Your instruction" (confidence null).
- `classify_preview_guardrail_ask.json`: a configured payer whose payment looks like the other kind; the payment is asked (source RULE) with the guardrail reason first.
- `learning_M001.json`: `payers` lists both instruction lists (`FAMILY_INSTRUCTION`, `CUSTOMER_INSTRUCTION`) with `source` (`SETUP` / `CONFIRMATION` / `ANSWERS`), plus `MIXED` and `MEMORY`; new `customer_payers_configured`. Numbers are placeholders.
- `merchant_M001.json` has `customer_payers`.

## Confidence display (frontend: Asitha)
The API sends the real number (`0.9971`). Show a confidence ≥ 0.995 as **">99%"**, never "100%". `null` (`confidence_kind: NONE`) shows **"Your instruction"**, never a percentage.

## Summary states for the Today screen
- `summary_M001_morning`: after the 05:40 expense, profit −₹3,100
- `summary_M001_before_confirm`: after payment 15, ₹2,000 pending
- `summary_M001_after_confirm`: after Murugan answers FAMILY

Checks already run on these files: reconciliation identity holds, profit = sales − expenses, notice ledger view adds up, ledger hash chain links.
