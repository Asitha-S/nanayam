"""Hash chain for ledger entries (DATA_AND_LOGIC section 7.2).

Confidence is a 4-decimal string in the database and in the canonical form ("0.7100"), a JSON
number in the API. Conversion happens only through confidence_to_db / confidence_from_db.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Mapping

GENESIS_PREV_HASH = "0" * 64

HASH_FIELDS = (
    "merchant_id",
    "seq",
    "entry_type",
    "source_type",
    "source_id",
    "supersedes_entry_id",
    "amount_paise",
    "classification",
    "classification_source",
    "confidence",
    "expense_category",
    "effective_at",
    "created_at",
    "prev_hash",
)


def confidence_to_db(x: float | None) -> str | None:
    return None if x is None else f"{x:.4f}"


def confidence_from_db(s: str | None) -> float | None:
    return None if s is None else float(s)


def canonical(entry: Mapping) -> str:
    """entry must hold the DB form (confidence as a 4 dp string or None)."""
    missing = [f for f in HASH_FIELDS if f not in entry]
    if missing:
        raise KeyError(f"ledger entry missing hash fields: {missing}")
    conf = entry["confidence"]
    if conf is not None and not isinstance(conf, str):
        raise TypeError("confidence must be the 4 dp DB string when hashing")
    body = {f: entry[f] for f in HASH_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(entry: Mapping) -> str:
    return hashlib.sha256(canonical(entry).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifyResult:
    status: str  # VALID | TAMPERED
    entries_checked: int
    first_invalid_entry_id: str | None
    problem: str | None  # hash_mismatch | prev_hash_mismatch | None


def verify_chain(entries: Iterable[Mapping]) -> VerifyResult:
    """entries: one merchant's rows in seq order (DB form). Stops at the first failure."""
    expected_prev = GENESIS_PREV_HASH
    expected_seq = 1
    checked = 0
    for e in entries:
        checked += 1
        if e["seq"] != expected_seq or e["prev_hash"] != expected_prev:
            return VerifyResult("TAMPERED", checked, e["ledger_entry_id"], "prev_hash_mismatch")
        if compute_hash(e) != e["hash"]:
            return VerifyResult("TAMPERED", checked, e["ledger_entry_id"], "hash_mismatch")
        expected_prev = e["hash"]
        expected_seq += 1
    return VerifyResult("VALID", checked, None, None)
