# Frontend: start here

Status on 14 Nov 2026: we are choosing the visual direction for the landing page. Nothing in React exists yet; it is built once a direction is picked.

## 1. Look at the directions and pick one

1. Get the branch:

   ```bash
   git fetch origin
   git checkout asitha/frontend
   git pull
   ```

2. Open `frontend/explore/directions/index.html` in Chrome (double-click it in the file explorer). It needs internet for the fonts.

   If double-clicking shows blank cards, serve the folder instead:

   ```bash
   cd frontend/explore/directions
   python -m http.server 5500
   ```

   and open http://localhost:5500

3. Each card is a sketch of the **first screen only** (1440 × 900), not the finished page. Click **Open full size**, then press F11 to see it the way the projector will.

4. Send Asitha the name of the direction you want (for example "Passbook: the ledger line" or "Sivakasi label press") and one line on what you like or dislike. Mixing is fine to suggest ("Passbook, but with the Sivakasi colours"); she decides.

The seven directions:

| Round | Name | Idea in one line |
|---|---|---|
| 2 | Sivakasi label press | Matchbox-label press sheet; uncertain payments print out of register until answered |
| 2 | Kanchipuram kasu border | Silk border of gold coin motifs, one per payment; family money woven in green |
| 2 | Glass colour-field partition | Black-barred glass panes; colour means sales, expenses or family |
| 1 | Passbook: the ledger line | One UPI credit line printed huge, stamped வீட்டு பணம் (family money, not a sale) |
| 1 | Daily sheet calendar | The kadai tear-off calendar with today's profit on the sheet |
| 1 | Painted cinema hoarding | நாணயம் in billboard lettering, three proofs as vignettes |
| 1 | Plain fintech page | The safe standard: headline left, phone right |

## 2. What happens after the pick

1. Asitha builds the landing page and the P1 screens (Soundbox simulator, question card, Talk, Today, Ledger) in React (Vite) in this folder, on the chosen direction.
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

- The older boards in `frontend/explore` (`a.html`, `b.html`, `c.html`) were rejected and are kept only for reference.
- `frontend/.impeccable/` holds working files from the Impeccable design tool. Its live decision page runs only on Asitha's laptop; you don't need it, the gallery above shows the same directions.
