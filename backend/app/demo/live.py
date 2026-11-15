"""Live mode (demo tools): payments that arrive on their own, and the payer list for the customer /pay page.

A live payment is sampled from the merchant's own payers with the generator's patterns (data/generator/params.py,
DATA_AND_LOGIC 4.2-4.3) and then goes through exactly the same path as POST /payments (services.payments
.create_payment), with a unique transaction_id and the backend's current time (clock.now(): the real time of day on
DEMO_DATE unless DEMO_TIME pins it). Nothing here changes how a payment is classified.
"""
from __future__ import annotations

import ipaddress
import json
import math
import random
import socket
import sqlite3

from .. import clock, errors, repo
from ..udhari import seed as udhari_seed
from ..config import DEMO_DATA_DIR
from ..schemas import PaymentIn
from ..services import payments

# copied from data/generator/params.py (the backend does not import the generator package)
CATEGORY = {
    "VEGETABLES": {"median": 120, "sigma": 0.8, "lo": 10, "hi": 2500},
    "FRUITS": {"median": 180, "sigma": 0.75, "lo": 20, "hi": 3000},
    "FLOWERS": {"median": 60, "sigma": 0.7, "lo": 10, "hi": 1500},
    "TEA_STALL": {"median": 25, "sigma": 0.5, "lo": 10, "hi": 300},
    "MIXED_KIRANA": {"median": 150, "sigma": 0.9, "lo": 10, "hi": 4000},
}
ROUND_TO_5 = 0.60
CUSTOMER_P2M = 0.85
BUSINESS_AMOUNT = (600, 1500)
FAMILY_AMOUNTS = [1000, 1500, 2000, 3000]
NEW_PERSON_AMOUNTS = [1000, 2000, 3000, 5000]
WALKIN_NAMES = ["Muthu", "Selvam", "Anitha", "Ravi", "Deepa", "Kumar", "Priya", "Suresh", "Lavanya", "Murali"]
# share of live payments by kind: mostly regular customers' small sales, a bulk buyer now and then,
# walk-ins, and rarely a round P2P transfer from family or from someone new (the ones Naanayam may ask about)
MIX = [("customer", 0.80), ("business", 0.08), ("walkin", 0.07), ("family", 0.04), ("new_person", 0.01)]


def _demo_day(merchant_id: str) -> dict | None:
    path = DEMO_DATA_DIR / f"{merchant_id}_demo_day.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pay_options(conn: sqlite3.Connection, merchant_id: str) -> dict:
    """Who can pay this merchant on the /pay page and in live mode: frequent customers, the bulk buyer,
    configured family, and the people in the merchant's demo day. No classification hints (the phone sees this)."""
    m = repo.require_merchant(conn, merchant_id)
    family = {r["payer_id"]: r for r in conn.execute(
        "SELECT f.payer_id, p.payer_name, p.payer_vpa_kind FROM merchant_family_payers f JOIN payers p USING (payer_id)"
        " WHERE f.merchant_id = ?", (merchant_id,))}
    ranked = conn.execute(
        "SELECT pa.payer_id, py.payer_name, py.payer_vpa_kind, COUNT(*) AS n,"
        " SUM(pa.payment_type = 'P2M') AS p2m FROM payments pa JOIN payers py USING (payer_id)"
        " WHERE pa.merchant_id = ? GROUP BY pa.payer_id ORDER BY n DESC, pa.payer_id LIMIT 60", (merchant_id,)).fetchall()
    customers = [r for r in ranked if r["payer_vpa_kind"] == "PERSONAL" and r["payer_id"] not in family and r["n"] >= 5][:6]
    business = [r for r in ranked if r["payer_vpa_kind"] == "BUSINESS"][:2]
    people: dict[str, dict] = {pid: {"payer_id": pid, "payer_name": r["payer_name"], "payer_vpa_kind": r["payer_vpa_kind"]}
                               for pid, r in family.items()}
    day = _demo_day(merchant_id) or {}
    known = {c["payer_id"] for c in customers} | {b["payer_id"] for b in business}
    for item in day.get("payments", []):
        p = item.get("request", item)
        if p.get("payment_type") == "P2P" and p["payer_id"] not in known:
            people.setdefault(p["payer_id"], {"payer_id": p["payer_id"], "payer_name": p["payer_name"],
                                              "payer_vpa_kind": p["payer_vpa_kind"]})

    def row(r, role, usual):
        return {"payer_id": r["payer_id"], "payer_name": r["payer_name"], "payer_vpa_kind": r["payer_vpa_kind"],
                "role": role, "usual_payment_type": usual}

    return {
        "merchant_id": merchant_id,
        "display_name": m["display_name"],
        "payers": [row(r, "CUSTOMER", "P2M" if (r["p2m"] or 0) * 2 >= r["n"] else "P2P") for r in customers]
                  + [row(r, "BUSINESS", "P2M") for r in business]
                  + [row(p, "PERSON", "P2P") for p in sorted(people.values(), key=lambda x: x["payer_name"])],
    }


def _customer_rupees(rng: random.Random, category: str) -> int:
    c = CATEGORY.get(category, CATEGORY["VEGETABLES"])
    r = int(round(c["median"] * math.exp(c["sigma"] * rng.gauss(0, 1))))
    if rng.random() < ROUND_TO_5:
        r = int(round(r / 5) * 5)
    return max(c["lo"], min(c["hi"], r))


def _new_payer_id(conn: sqlite3.Connection, rng: random.Random, prefix: str) -> str:
    for _ in range(50):
        pid = f"{prefix}{rng.randrange(10**5, 10**6)}"
        if conn.execute("SELECT 1 FROM payers WHERE payer_id = ?", (pid,)).fetchone() is None:
            return pid
    raise errors.invalid_state("Could not allocate a new payer id")


def sample(conn: sqlite3.Connection, merchant_id: str, rng: random.Random) -> dict:
    """One live payment's fields (payer, amount, type), drawn with the generator's patterns."""
    m = repo.require_merchant(conn, merchant_id)
    opts = pay_options(conn, merchant_id)["payers"]
    by_role = {role: [p for p in opts if p["role"] == role] for role in ("CUSTOMER", "BUSINESS", "PERSON")}
    family_ids = {r["payer_id"] for r in conn.execute("SELECT payer_id FROM merchant_family_payers WHERE merchant_id = ?",
                                                       (merchant_id,))}
    kinds = [k for k, _ in MIX]
    kind = rng.choices(kinds, weights=[w for _, w in MIX])[0]
    if kind == "business" and not by_role["BUSINESS"]:
        kind = "customer"
    if kind == "family" and not family_ids:
        kind = "new_person"
    if kind == "customer" and by_role["CUSTOMER"]:
        p = rng.choice(by_role["CUSTOMER"])
        return {**p, "amount_rupees": _customer_rupees(rng, m["business_category"]),
                "payment_type": "P2M" if rng.random() < CUSTOMER_P2M else "P2P"}
    if kind == "business":
        p = rng.choice(by_role["BUSINESS"])
        return {**p, "amount_rupees": int(round(rng.randint(*BUSINESS_AMOUNT) / 10) * 10), "payment_type": "P2M"}
    if kind == "family":
        p = next(x for x in by_role["PERSON"] if x["payer_id"] in family_ids) if any(
            x["payer_id"] in family_ids for x in by_role["PERSON"]) else None
        if p is not None:
            return {**p, "amount_rupees": rng.choice(FAMILY_AMOUNTS), "payment_type": "P2P"}
        kind = "new_person"
    if kind == "new_person":
        name = f"{rng.choice(WALKIN_NAMES)} {rng.choice('ABDKMRS')}"
        return {"payer_id": _new_payer_id(conn, rng, "P9"), "payer_name": name, "payer_vpa_kind": "PERSONAL",
                "role": "PERSON", "amount_rupees": rng.choice(NEW_PERSON_AMOUNTS), "payment_type": "P2P"}
    # walk-in (or no regulars yet): a first-time customer paying the shop QR
    return {"payer_id": _new_payer_id(conn, rng, "P1"), "payer_name": rng.choice(WALKIN_NAMES), "payer_vpa_kind": "PERSONAL",
            "role": "CUSTOMER", "amount_rupees": _customer_rupees(rng, m["business_category"]), "payment_type": "P2M"}


def live_payment(conn: sqlite3.Connection, merchant_id: str, rng: random.Random | None = None) -> tuple[int, dict]:
    """Sample one payment and send it through the POST /payments path, at the backend's current time."""
    rng = rng or random.Random()
    # UDHARI on: the seeded customer pays part of the tab first (once a day); the payment is classified as usual
    s = udhari_seed.live_payer(conn, merchant_id) or sample(conn, merchant_id, rng)
    now = clock.now()
    for _ in range(5):
        txn = f"LIVE-{merchant_id}-{now:%Y%m%d-%H%M%S}-{rng.randrange(16**4):04x}"
        if conn.execute("SELECT 1 FROM payments WHERE transaction_id = ?", (txn,)).fetchone() is None:
            break
    req = PaymentIn(transaction_id=txn, merchant_id=merchant_id, payer_id=s["payer_id"], payer_name=s["payer_name"],
                    payer_vpa_kind=s["payer_vpa_kind"], amount_paise=s["amount_rupees"] * 100,
                    payment_type=s["payment_type"], timestamp=clock.iso(now), description=None)
    status, body = payments.create_payment(conn, req)
    return status, {**body, "payer_name": s["payer_name"], "timestamp": clock.iso(now), "payment_type": s["payment_type"]}


def lan_addresses() -> list[str]:
    """This machine's private LAN IPv4 addresses (for the /pay QR code), most likely first."""
    found: list[str] = []
    try:  # the address the OS would use to reach the network (no packet is sent)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    out = []
    for ip in dict.fromkeys(found):
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_private and not a.is_loopback and not a.is_link_local:
            out.append(ip)
    return sorted(out, key=lambda ip: (not ip.startswith("192.168."), not ip.startswith("10."), ip))
