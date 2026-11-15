# Frontend: start here

React (Vite) app for Naanayam: a landing page for judges and the app screens, all on one design system. Light theme only.

## Run it

1. Backend (from the repo root, in its own terminal):

   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000        # http://localhost:8000/api/health
   ```

2. Frontend (in another terminal):

   ```bash
   cd frontend
   npm install            # first time only
   npm run dev            # http://localhost:5173
   ```

   The app talks to `http://localhost:8000/api` (CORS allows port 5173). To work without a backend, create
   `frontend/.env` with `VITE_API_BASE=fixtures`: every screen then reads `contract/fixtures/`, and writes return the
   fixture responses (nothing is saved).

3. Production build: `npm run build` (output in `frontend/dist`, gitignored).

## Screens

| Route | Screen | Main endpoints |
|---|---|---|
| `#/` | Landing page (overview for judges) | `/health`, `/demo/script`, `/merchants/{id}/summary`, `/evaluation`, `/passport`, `/ledger/verify` |
| `#/soundbox` | Soundbox simulator | `POST /demo/next-payment`, `/audio/{id}` |
| `#/questions` | Question card and remember prompt | `/merchants/{id}/questions`, `POST /payments/{txn}/confirm` |
| `#/talk` | Talk: text first, mic second | `/voice/transcribe`, `/voice/interpret`, `/voice/answer`, `POST /expenses` |
| `#/today` | Today: proof of profit | `/merchants/{id}/summary?include_sources=true`, exports |
| `#/ledger` | Ledger: entries, detail, verify | `/merchants/{id}/ledger`, `/ledger/{entry_id}`, `/ledger/verify` |
| `#/learning` | Learning and held-out evaluation | `/merchants/{id}/learning`, `/evaluation`, `POST /classify/preview` |
| `#/notice` | Notice mode | `/tax-summary`, `POST /notices/analyse`, `/notices/{id}/evidence`, exports |
| `#/passport` | Credit passport (shown only) | `/merchants/{id}/passport` |
| `#/demo` | Demo control panel (hidden, not in the menu) | `/health`, `POST /demo/reset`, `/demo/script`, `POST /demo/tamper` |

The merchant switch in the top bar changes between Murugan (M001, Tamil) and Venkatesh (M002, Telugu).

## Where things live

- `src/api.js`: every request; `useApi(path)` refetches after any write. `VITE_API_BASE=fixtures` mapping is here.
- `src/app/`: merchant context (`useMerchant`) and hash routing.
- `src/components/`: page chrome (`Shell.jsx`, `AppShell.jsx`) and shared atoms in `ui.jsx` (`Money`, `Badge`, `confidenceText`, …).
- `src/styles/`: `tokens.css` (colours, type, radii), `landing.css` (chrome and landing), `app.css` (shared screen patterns), one file per screen.
- `src/pages/`: one file per screen.

## Rules that apply to every screen

- Light theme only.
- Never compute money in the frontend. Show the backend's `amount_display` through `<Money>`; every amount opens the ledger entries it came from.
- Tamil text at 22px or more in Noto Sans Tamil; Telugu in Noto Sans Telugu (set `lang="ta"` / `lang="te"`).
- Evaluation numbers come only from `GET /evaluation` and always show its `data_label`. Never type a metric by hand.
- Recorded demo clips are labelled "Recorded demo clip". Confidence above 99% shows as ">99%", never "100%".
- Endpoint names, fields and enums come from `contract/API_CONTRACT.md` and never change from the frontend side.

Product facts the design must keep are in `frontend/PRODUCT.md`.

## Notes

- Everything in `frontend/explore` is earlier exploration, kept only as a record. Don't build from it.
- `frontend/.impeccable/` holds local working files from the Impeccable design tool; you don't need them.
