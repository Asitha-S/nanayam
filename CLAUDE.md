# Instructions for Claude Code

Read `PROJECT.md`, `contract/API_CONTRACT.md` and the doc for your area in `docs/` before working.

- Only edit folders you own (PROJECT.md section 5). Ask the owner for changes elsewhere.
- Never change endpoint names, field names, enums or status codes. Propose changes in `contract/CHANGES.md`.
- Money is integer paise; display strings come from `backend/app/money.py`. Time is IST; get "now" only from `backend/app/clock.py`.
- The ledger is append-only. No `UPDATE`/`DELETE` on append-only tables (a test enforces this).
- Never call Sarvam directly; use `backend/app/sarvam/client.py`.
- Never commit `.env` or API keys.

## Commits

**Do not add AI co-author or attribution lines to commits or pull requests.** No `Co-Authored-By: Claude ...` trailer, no "Generated with Claude Code" line. Commit messages contain only the change description.
