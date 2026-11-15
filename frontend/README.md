# Frontend: start here

Status on 14 Nov 2026: the visual direction is decided. We are building from a reference UI that Asitha chose (light theme). Nothing in React exists yet.

## 1. The design reference

- The UI follows one existing light-theme interface, used as the reference for layout, type and feel. Asitha will add screenshots of it to this folder; until they are in, ask her to show you the reference.
- The direction sketches in `frontend/explore/directions/` are **no longer being picked from**. They stay only as a record of what was explored.
- Get the branch to see everything:

  ```bash
  git fetch origin
  git checkout asitha/frontend
  git pull
  ```

## 2. What happens next

1. Asitha builds the landing page and the P1 screens (Soundbox simulator, question card, Talk, Today, Ledger) in React (Vite) in this folder, following the reference.
2. The colours, fonts, spacing and components are written down in `frontend/DESIGN.md`. Every later screen follows it.
3. Nagasai builds the remaining screens on those same components: learning / evaluation, notice mode, credit passport, the Telugu flow.
4. Run steps for the React app (`npm install`, `npm run dev`, `VITE_API_BASE`) are added to this README when the app exists.

Product facts the design must keep are in `frontend/PRODUCT.md`.

## 3. Rules that apply to every screen

- Light theme only.
- Never compute money in the frontend. Show the backend's `amount_display`; every amount opens the ledger entries it came from.
- Tamil text at 22px or more in Noto Sans Tamil; Telugu in Noto Sans Telugu.
- Evaluation numbers come only from `GET /evaluation` and are labelled "Synthetic data". Never type a metric by hand.
- Recorded demo clips are labelled "Recorded demo clip". Confidence above 99% shows as ">99%", never "100%".
- Endpoint names, fields and enums come from `contract/API_CONTRACT.md` and never change from the frontend side.

## Notes

- Everything in `frontend/explore` (the `a.html` / `b.html` / `c.html` boards and the `directions/` gallery) is earlier exploration, kept only as a record. Don't build from it.
- `frontend/.impeccable/` holds local working files from the Impeccable design tool; you don't need them.
