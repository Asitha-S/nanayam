"""The fixture ledger (17 demo-day entries) was hashed with the DATA_AND_LOGIC 7.2 formula.
Our implementation must reproduce every hash exactly."""
import copy
import json

from app.config import FIXTURES_DIR
from app.ledger.hashing import compute_hash, confidence_from_db, confidence_to_db, verify_chain


def _db_rows():
    data = json.loads((FIXTURES_DIR / "ledger_M001_2026-11-15.json").read_text(encoding="utf-8"))
    rows = []
    for item in data["items"]:
        row = dict(item, merchant_id=data["merchant_id"])
        row["confidence"] = confidence_to_db(item["confidence"])  # API number -> DB string
        rows.append(row)
    return rows


def test_fixture_hashes_reproduce():
    for row in _db_rows():
        assert compute_hash(row) == row["hash"], row["ledger_entry_id"]


def test_fixture_chain_links():
    rows = _db_rows()
    for prev, cur in zip(rows, rows[1:]):
        assert cur["prev_hash"] == prev["hash"]


def test_confidence_format():
    assert confidence_to_db(0.71) == "0.7100"
    assert confidence_to_db(0.98) == "0.9800"
    assert confidence_to_db(None) is None
    assert confidence_from_db("0.7100") == 0.71


def _renumbered(rows):
    """Turn the fixture slice into a chain starting at seq 1 so verify_chain can walk it."""
    out, prev = [], "0" * 64
    for i, r in enumerate(copy.deepcopy(rows), start=1):
        r["seq"], r["prev_hash"] = i, prev
        r["hash"] = compute_hash(r)
        prev = r["hash"]
        out.append(r)
    return out


def test_verify_valid():
    result = verify_chain(_renumbered(_db_rows()))
    assert result.status == "VALID" and result.entries_checked == 17


def test_verify_detects_edited_amount():
    rows = _renumbered(_db_rows())
    rows[5]["amount_paise"] += 100
    result = verify_chain(rows)
    assert (result.status, result.first_invalid_entry_id, result.problem) == (
        "TAMPERED", rows[5]["ledger_entry_id"], "hash_mismatch",
    )


def test_verify_detects_deleted_row():
    rows = _renumbered(_db_rows())
    del rows[3]
    result = verify_chain(rows)
    assert result.status == "TAMPERED" and result.problem == "prev_hash_mismatch"
