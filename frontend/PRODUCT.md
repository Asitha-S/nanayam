# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React (Vite), per PROJECT.md. Talks to the FastAPI backend at `VITE_API_BASE` (default `http://localhost:8000/api`; `fixtures` serves `contract/fixtures/`). Light theme only (user decision, 2026-11-14).

## Users

- **Hackathon judges first** (Paytm Build for India AI Hackathon, Chennai, 15 Nov 2026, Track 1: Merchant Growth AI). They have minutes per team; they need to grasp what Naanayam does, see it work, and open the live demo.
- **Small merchants, as the story the judges follow.** Murugan, 45, runs Murugan Kaaikari Kadai, a vegetable stall in Chennai; buys stock at Koyambedu; takes UPI on a Paytm Soundbox; speaks Tamil. Second merchant: Venkatesh, Venkatesh Pandla Dukanam (fruits, Telugu). Third: Ravi Stores (mixed kirana, Tamil).

## Product Purpose

From payment collections to financial proof. The Soundbox tells a merchant what came in; Naanayam turns incoming UPI payments and voice-logged expenses into a structured, traceable, append-only ledger, so the merchant knows what they earned, can explain what they received, and can show what the business is worth. Success on the landing page: a judge understands this within one screen and opens the live demo.

## Positioning

Naanayam (நாணயம்: coin, and honesty) separates business sales from family money (family, friends, loan repayments to the owner) in a merchant's UPI collections. Confident calls happen silently; uncertain ones become one Tamil or Telugu question with two big answers; the merchant's answers teach that merchant's future payments. The backend calculates every rupee; voice only speaks numbers the backend already calculated. One ledger yields three proofs: profit for the merchant, evidence for a GST notice (for a CA), a credit passport for a lender. Voice is the interface; the intelligent ledger is the product. Never a chatbot, copilot or assistant.

## Operating Context

- Demo day: a projector in a hall, plus a laptop and a phone; the backend runs locally (`DEMO_TIME` pinned to 21:30 IST); the demo never depends on live internet.
- Murugan's scripted day (M001, 15 Nov 2026): sales ₹4,820, expenses ₹3,100 (Koyambedu vegetables, logged by voice), recorded profit ₹1,720; family payments from Lakshmi R (Akka) and Karthik (Thambi) kept out of sales; one Tamil question card asked on the Soundbox.
- Screens after the landing page (P1): Soundbox simulator, question card, Talk, Today, Ledger. Later: learning/evaluation, notice mode, CA export, credit passport, Telugu flow.

## Capabilities and Constraints

- Contract is frozen: `contract/API_CONTRACT.md`. Endpoint names, fields, enums, status codes never change from the frontend side.
- The frontend never computes money, confidence or GST treatment. Every amount shown is the backend's `amount_display`; every amount is tappable to its ledger entries.
- Evaluation numbers come only from `GET /evaluation` (an actual run) and are labelled "Synthetic data". Never typed into the UI by hand.
- Recorded demo clips are labelled "Recorded demo clip"; never presented as live.
- Source badges: "Recorded demo clip", "Your instruction", "From notice", "From your ledger"; confidence above 99% displays as ">99%", never "100%".
- Not built: real Paytm/bank/NPCI/GST integration (all payments synthetic), tax filing, legal advice, loan decisions, credit scores.

## Brand Commitments

- Name: Naanayam, with the Tamil word நாணயம் and its double meaning (coin, honesty).
- Tagline in use: "From payment collections to financial proof."
- Tamil text at 22px or more, Noto Sans Tamil; Telugu in Noto Sans Telugu. High contrast for a projector.
- Light theme only.

## Evidence on Hand

- Demo data: `contract/fixtures/` (summary before/after confirm, question card, ledger, verify valid/tampered, passport, notice evidence, evaluation), `data/demo/seed.db`.
- Evaluation (holdout run holdout-20261114-154347-2e5850, synthetic, generator seed 42; 110 test merchants, 153,192 test payments): family money found 645 of 667 with learning vs 630 baseline vs 0 for always-SALE; income wrongly removed 26 of 152,525; questions per merchant per day 0.44 (baseline 0.48). Served by `GET /evaluation`.
- Sample GST notice amount ₹8,42,162 (`data/demo/notice_numbers.json`).
- No real customers, testimonials, press, partners or pilots. None may be invented. No photographs of real merchants exist.

## Product Principles

1. Proof over claims: every figure on screen links to the entries it came from.
2. Ask, don't guess: uncertainty is shown honestly and becomes one question.
3. The merchant's words and the merchant's language come first.
4. Small and honest labels: say where each thing came from.

## Accessibility & Inclusion

Tamil-first merchants with varying literacy: large type (Tamil ≥ 22px), big tap targets, two-choice answers, voice alongside text. Projector legibility: high contrast, nothing below 16px on the landing page.
