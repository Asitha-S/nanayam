"""The committed demo seed (data/demo/seed.db, built by python -m data.seed_demo)."""
import hashlib
import json
import random
import sqlite3
from datetime import date, timedelta

import pytest

from app.config import DEMO_DATA_DIR
from app.finance.summary import compute
from app.ledger.hashing import verify_chain

SEED = DEMO_DATA_DIR / "seed.db"
META = DEMO_DATA_DIR / "seed_meta.json"
pytestmark = [pytest.mark.skipif(not SEED.exists(), reason="run python -m data.seed_demo first"),
              pytest.mark.timeout(900)]


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(f"file:{SEED.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture(scope="module")
def meta():
    return json.loads(META.read_text(encoding="utf-8"))


def test_exactly_three_open_questions_all_29_to_31_october(conn):
    rows = conn.execute(
        "SELECT q.merchant_id, p.timestamp, py.payer_name, p.amount_paise, p.payment_type FROM questions q"
        " JOIN payments p USING (transaction_id) JOIN payers py ON py.payer_id = p.payer_id"
        " WHERE q.status = 'OPEN' ORDER BY p.timestamp"
    ).fetchall()
    assert len(rows) == 3
    assert {r["merchant_id"] for r in rows} == {"M001"}
    assert [r["timestamp"][:10] for r in rows] == ["2026-10-29", "2026-10-30", "2026-10-31"]
    assert [r["payer_name"] for r in rows] == ["Mani", "Jaya", "Prabhu"]
    assert all(r["timestamp"][11:16] == "20:05" and r["payment_type"] == "P2P" for r in rows)


def test_every_other_question_answered_correctly_by_simulated_merchant(conn):
    unanswered = conn.execute("SELECT COUNT(*) FROM questions q WHERE status = 'ANSWERED' AND NOT EXISTS"
                              " (SELECT 1 FROM feedback f WHERE f.transaction_id = q.transaction_id)").fetchone()[0]
    assert unanswered == 0
    # feedback only from answers, at most one per payment in the seed
    assert conn.execute("SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM feedback").fetchone()[0] == 0


def test_nothing_on_or_after_demo_date(conn):
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE timestamp >= '2026-11-15'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM expenses WHERE timestamp >= '2026-11-15'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE payer_id IN ('P90001', 'P90011')").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM payments WHERE transaction_id LIKE 'TXN-M00_-20261115-%'").fetchone()[0] == 0


def test_ledger_chains_valid_and_created_at_historical(conn):
    for mid in ("M001", "M002", "M003"):
        rows = conn.execute("SELECT * FROM ledger_entries WHERE merchant_id = ? ORDER BY seq", (mid,)).fetchall()
        assert verify_chain(rows).status == "VALID", mid
        assert rows[-1]["created_at"] < "2026-11-15", mid  # history written at its own time
        created = [r["created_at"] for r in rows]
        assert created == sorted(created)


def test_reconciliation_identity_on_random_periods(conn):
    rng = random.Random(7)
    start0 = date(2026, 8, 1)
    for _ in range(25):
        mid = rng.choice(["M001", "M002", "M003"])
        a = start0 + timedelta(days=rng.randrange(0, 106))
        b = a + timedelta(days=rng.randrange(0, 30))
        assert compute(conn, mid, a, b).reconciliation_ok, (mid, a, b)
    assert compute(conn, "M001", date(2026, 8, 1), date(2026, 11, 14)).reconciliation_ok


def test_karthik_is_configured_family(conn):
    rows = conn.execute(
        "SELECT le.classification, le.classification_source, le.confidence FROM ledger_entries le"
        " JOIN payments p ON p.transaction_id = le.source_id WHERE p.payer_id = 'P90002' AND le.entry_type = 'PAYMENT_IN'"
    ).fetchall()
    assert len(rows) >= 12
    assert all((r[0], r[1], r[2]) == ("FAMILY", "MERCHANT_CONFIG", None) for r in rows)


def test_single_file_database(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert not (DEMO_DATA_DIR / "seed.db-wal").exists()


def test_seed_meta(conn, meta):
    assert meta["seed_db_sha256"] == hashlib.sha256(SEED.read_bytes()).hexdigest()
    assert set(meta["label_mix"]) == {"count_share", "value_share"}
    assert meta["label_mix"]["value_share"]["overall"] > meta["label_mix"]["count_share"]["overall"]
    for mid, counts in meta["counts"].items():
        assert counts["payments"] == conn.execute("SELECT COUNT(*) FROM payments WHERE merchant_id = ?", (mid,)).fetchone()[0]
    assert meta["counts"]["M001"]["questions_open"] == 3
    assert meta["replay"]["left_unanswered"] == 3 and meta["replay"]["answer_skipped_reversed"] == 0
    assert meta["placeholder_classifier"] == (meta["model_version"] == "placeholder-rule-not-a-model")


def test_notice_numbers_match_seed(conn, meta):
    notice = json.loads((DEMO_DATA_DIR / "notice_numbers.json").read_text(encoding="utf-8"))
    gross = conn.execute("SELECT SUM(amount_paise) FROM payments WHERE merchant_id = 'M001'"
                         " AND substr(timestamp, 1, 10) BETWEEN '2026-08-01' AND '2026-10-31'").fetchone()[0]
    assert notice["amount_questioned_paise"] == gross
    assert notice["seed_db_sha256"] == meta["seed_db_sha256"]


def test_demo_state_starts_at_one(conn):
    assert dict(conn.execute("SELECT merchant_id, next_demo_index FROM demo_state").fetchall()) == {"M001": 1, "M002": 1}


def test_named_demo_payers_are_fixtures_not_simulated(conn, meta):
    from data.generator.generate import NAMED_PAYERS

    remembered = conn.execute("SELECT payer_id FROM merchant_family_payers WHERE added_via = 'CONFIRMATION'"
                              " UNION SELECT payer_id FROM merchant_customer_payers").fetchall()
    assert not {r[0] for r in remembered} & set(NAMED_PAYERS)
    assert meta["remember"]["never_for"] == sorted(NAMED_PAYERS)


def test_selvi_stays_mixed(conn):
    from app.feedback.memory import payer_counts

    conn.row_factory = sqlite3.Row
    n_family, n_sale = payer_counts(conn, "M001", "P90003")
    assert (n_family, n_sale) == (3, 2)  # MIXED: rule 5a, always asked
    assert not conn.execute("SELECT 1 FROM merchant_family_payers WHERE payer_id = 'P90003'").fetchone()
    assert not conn.execute("SELECT 1 FROM merchant_customer_payers WHERE payer_id = 'P90003'").fetchone()
