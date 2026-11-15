"""Demo-day scripts data/demo/M001_demo_day.json and M002_demo_day.json (DATA_AND_LOGIC 3.3, 3.4).

Amounts, times, payment types and expected outcomes are the fixed values from the spec. M001's
customer IDs are fixed in the spec; M002's are picked from M002's existing regular customers
(at least 5 prior payments, personal handle) and frozen here. Regenerating with the same seed
gives the same files.
"""
from __future__ import annotations

from .generate import IST, NAMED_PAYERS, Generated  # noqa: F401  (IST documents the offset used)

DEMO_DATE = "2026-11-15"
MIN_PRIOR_FOR_DEMO_CUSTOMER = 5

# (time, payer_id or None for "pick an existing M002 customer", type, rupees, expected action, expected final)
M001_PAYMENTS = [
    ("06:12", "P10411", "P2M", 40, "AUTO_CLASSIFY", "SALE"),
    ("06:30", "P10057", "P2M", 60, "AUTO_CLASSIFY", "SALE"),
    ("06:58", "P10233", "P2M", 120, "AUTO_CLASSIFY", "SALE"),
    ("07:25", "P10019", "P2M", 85, "AUTO_CLASSIFY", "SALE"),
    ("07:50", "P10388", "P2M", 200, "AUTO_CLASSIFY", "SALE"),
    ("08:40", "P10102", "P2M", 150, "AUTO_CLASSIFY", "SALE"),
    ("09:15", "P10276", "P2M", 75, "AUTO_CLASSIFY", "SALE"),
    ("10:05", "P10040", "P2M", 310, "AUTO_CLASSIFY", "SALE"),
    ("11:20", "P10345", "P2M", 45, "AUTO_CLASSIFY", "SALE"),
    ("12:40", "P10150", "P2M", 500, "AUTO_CLASSIFY", "SALE"),
    ("16:05", "P10077", "P2M", 230, "AUTO_CLASSIFY", "SALE"),
    ("17:10", "P20001", "P2M", 1200, "AUTO_CLASSIFY", "SALE"),
    ("18:20", "P10012", "P2M", 905, "AUTO_CLASSIFY", "SALE"),
    ("19:05", "P20001", "P2M", 900, "AUTO_CLASSIFY", "SALE"),
    ("19:42", "P90001", "P2P", 2000, "ASK_MERCHANT", "FAMILY"),
]
M002_PAYMENTS = [
    ("07:10", None, "P2M", 300, "AUTO_CLASSIFY", "SALE"),
    ("08:05", None, "P2M", 450, "AUTO_CLASSIFY", "SALE"),
    ("09:30", None, "P2M", 600, "AUTO_CLASSIFY", "SALE"),
    ("10:15", None, "P2M", 250, "AUTO_CLASSIFY", "SALE"),
    ("11:40", "P20011", "P2M", 800, "AUTO_CLASSIFY", "SALE"),
    ("13:20", "P20011", "P2M", 1200, "AUTO_CLASSIFY", "SALE"),
    ("15:05", None, "P2M", 350, "AUTO_CLASSIFY", "SALE"),
    ("16:45", None, "P2M", 900, "AUTO_CLASSIFY", "SALE"),
    ("18:10", None, "P2M", 700, "AUTO_CLASSIFY", "SALE"),
    ("19:00", None, "P2M", 800, "AUTO_CLASSIFY", "SALE"),
    ("19:50", "P90011", "P2P", 1500, "ASK_MERCHANT", "FAMILY"),
]

EXPENSES = {
    "M001": {"time": "05:40", "client_request_id": "6f1c2a8e-1d7b-4c2e-9b9a-0c3d2e1f4a5b", "rupees": 3100,
             "description": "Kaaikari, Koyambedu", "language": "ta",
             "utterance_text": "Koyambedu-la 3,100 rupees-ku kaaikari vaanginen"},
    "M002": {"time": "05:55", "client_request_id": "0b7d3c1e-5a2f-4e8b-9c6d-1f2e3a4b5c6d", "rupees": 4200,
             "description": "Pandlu, Koyambedu", "language": "te",
             "utterance_text": "Koyambedu lo 4,200 rupayalaku pandlu konnanu"},
}

# The merchant's answer to the ASK payment in the demo (DATA 3.3: "says remember").
ANSWERS = {
    "M001": {"confirmed_category": "FAMILY", "channel": "VOICE", "remember_payer": True,
             "utterance_text": "வீட்டு பணம், அக்கா அனுப்பினாங்க. ஆமா, எப்பவும்"},
    "M002": {"confirmed_category": "FAMILY", "channel": "VOICE", "remember_payer": True,
             "utterance_text": "ఇంటి డబ్బు, తమ్ముడు పంపాడు"},
}


def _payer_lookup(gen: Generated) -> dict[str, tuple[str, str]]:
    return {r.payer_id: (r.payer_name, r.payer_vpa_kind) for r in gen.payers.itertuples()}


def _m002_customers(gen: Generated, n: int) -> list[str]:
    counts = gen.payments[gen.payments.merchant_id == "M002"].payer_id.value_counts()
    payers = _payer_lookup(gen)
    chosen = [
        pid for pid in gen.regular_pools["M002"]
        if counts.get(pid, 0) >= MIN_PRIOR_FOR_DEMO_CUSTOMER and payers[pid][1] == "PERSONAL"
    ]
    if len(chosen) < n:
        raise RuntimeError("not enough established M002 customers for the demo script")
    return chosen[:n]


def build(gen: Generated, merchant_id: str) -> dict:
    payers = _payer_lookup(gen) | dict(NAMED_PAYERS)
    table = M001_PAYMENTS if merchant_id == "M001" else M002_PAYMENTS
    fill = iter(_m002_customers(gen, sum(1 for row in table if row[1] is None))) if merchant_id == "M002" else iter(())
    items = []
    for i, (hhmm, pid, ptype, rupees, action, final) in enumerate(table, start=1):
        pid = pid or next(fill)
        name, kind = payers[pid]
        items.append({
            "demo_index": i,
            "request": {
                "transaction_id": f"TXN-{merchant_id}-{DEMO_DATE.replace('-', '')}-{i:03d}",
                "merchant_id": merchant_id, "payer_id": pid, "payer_name": name, "payer_vpa_kind": kind,
                "amount_paise": rupees * 100, "payment_type": ptype,
                "timestamp": f"{DEMO_DATE}T{hhmm}:10+05:30", "description": None,
            },
            "expected_action": action,
            "expected_suggested_classification": final,
            "expected_final_classification": final,
        })
    e = EXPENSES[merchant_id]
    return {
        "merchant_id": merchant_id,
        "demo_date": DEMO_DATE,
        "generated_by": "python -m data.generator.run --seed 42",
        "expense": {
            "client_request_id": e["client_request_id"], "merchant_id": merchant_id,
            "amount_paise": e["rupees"] * 100, "category": "STOCK_PURCHASE", "description": e["description"],
            "timestamp": f"{DEMO_DATE}T{e['time']}:00+05:30", "input_source": "VOICE", "language": e["language"],
            "utterance_text": e["utterance_text"], "voice_log_id": None,
        },
        "payments": items,
        "answer": {"demo_index": len(items), **ANSWERS[merchant_id]},
    }
