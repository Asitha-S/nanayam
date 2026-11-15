"""SQLite schema and connections (DATA_AND_LOGIC section 1).

Money columns are INTEGER paise; timestamps are TEXT ISO 8601 with +05:30.
Append-only tables get INSERT-only repository functions; a test greps for UPDATE/DELETE on them.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

APPEND_ONLY_TABLES = (
    "payments",
    "predictions",
    "feedback",
    "refunds",
    "reversals",
    "expenses",
    "expense_voids",
    "ledger_entries",
    "tabs",
    "tab_entries",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id        TEXT PRIMARY KEY,
    display_name       TEXT NOT NULL,
    owner_name         TEXT NOT NULL,
    city               TEXT NOT NULL,
    business_category  TEXT NOT NULL CHECK (business_category IN ('VEGETABLES','FRUITS','FLOWERS','TEA_STALL','MIXED_KIRANA')),
    preferred_language TEXT NOT NULL CHECK (preferred_language IN ('ta','te','en')),
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payers (
    payer_id       TEXT PRIMARY KEY,
    payer_name     TEXT NOT NULL,
    payer_vpa_kind TEXT NOT NULL CHECK (payer_vpa_kind IN ('PERSONAL','BUSINESS'))
);

CREATE TABLE IF NOT EXISTS merchant_family_payers (
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    payer_id       TEXT NOT NULL REFERENCES payers(payer_id),
    relation_label TEXT,
    added_at       TEXT NOT NULL,
    added_via      TEXT NOT NULL CHECK (added_via IN ('SETUP','CONFIRMATION')),
    PRIMARY KEY (merchant_id, payer_id)
);

CREATE TABLE IF NOT EXISTS merchant_customer_payers (
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id),
    payer_id    TEXT NOT NULL REFERENCES payers(payer_id),
    added_at    TEXT NOT NULL,
    added_via   TEXT NOT NULL CHECK (added_via IN ('SETUP','CONFIRMATION')),
    PRIMARY KEY (merchant_id, payer_id)
);

CREATE TABLE IF NOT EXISTS payments (
    transaction_id TEXT PRIMARY KEY,
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    payer_id       TEXT NOT NULL REFERENCES payers(payer_id),
    amount_paise   INTEGER NOT NULL CHECK (amount_paise > 0),
    payment_type   TEXT NOT NULL CHECK (payment_type IN ('P2M','P2P')),
    timestamp      TEXT NOT NULL,
    description    TEXT,
    payload_hash   TEXT NOT NULL,
    received_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_payments_merchant_ts ON payments(merchant_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_payments_merchant_payer ON payments(merchant_id, payer_id);

CREATE TABLE IF NOT EXISTS predictions (
    transaction_id           TEXT PRIMARY KEY REFERENCES payments(transaction_id),
    model_version            TEXT,
    threshold                REAL NOT NULL,
    q_model                  REAL,
    p_final                  REAL,
    confidence               REAL,
    confidence_kind          TEXT NOT NULL CHECK (confidence_kind IN ('MODEL','NONE')),
    suggested_classification TEXT NOT NULL CHECK (suggested_classification IN ('SALE','FAMILY')),
    action                   TEXT NOT NULL CHECK (action IN ('AUTO_CLASSIFY','ASK_MERCHANT')),
    classification_source    TEXT NOT NULL CHECK (classification_source IN ('MERCHANT_CONFIG','PAYER_MEMORY','MODEL','RULE')),
    reasons_json             TEXT NOT NULL,
    created_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    question_id    TEXT PRIMARY KEY,
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    transaction_id TEXT NOT NULL UNIQUE REFERENCES payments(transaction_id),
    status         TEXT NOT NULL CHECK (status IN ('OPEN','ANSWERED')),
    created_at     TEXT NOT NULL,
    answered_at    TEXT
);
CREATE INDEX IF NOT EXISTS ix_questions_merchant_status ON questions(merchant_id, status);

CREATE TABLE IF NOT EXISTS feedback (
    feedback_id             TEXT PRIMARY KEY,
    merchant_id             TEXT NOT NULL REFERENCES merchants(merchant_id),
    transaction_id          TEXT NOT NULL REFERENCES payments(transaction_id),
    payer_id                TEXT NOT NULL REFERENCES payers(payer_id),
    confirmed_category      TEXT NOT NULL CHECK (confirmed_category IN ('SALE','FAMILY')),
    previous_classification TEXT NOT NULL CHECK (previous_classification IN ('SALE','FAMILY','PENDING')),
    q_model                 REAL,
    channel                 TEXT NOT NULL CHECK (channel IN ('TAP','VOICE')),
    utterance_text          TEXT,
    remember_payer          INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feedback_merchant_payer ON feedback(merchant_id, payer_id);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id      TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES payments(transaction_id),
    amount_paise   INTEGER NOT NULL CHECK (amount_paise > 0),
    timestamp      TEXT NOT NULL,
    reason         TEXT,
    payload_hash   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_refunds_txn ON refunds(transaction_id);

CREATE TABLE IF NOT EXISTS reversals (
    transaction_id TEXT PRIMARY KEY REFERENCES payments(transaction_id),
    timestamp      TEXT NOT NULL,
    reason         TEXT
);

CREATE TABLE IF NOT EXISTS expenses (
    expense_id        TEXT PRIMARY KEY,
    client_request_id TEXT NOT NULL UNIQUE,
    merchant_id       TEXT NOT NULL REFERENCES merchants(merchant_id),
    amount_paise      INTEGER NOT NULL CHECK (amount_paise > 0),
    category          TEXT NOT NULL CHECK (category IN ('STOCK_PURCHASE','TRANSPORT','PACKAGING','RENT','WAGES','UTILITIES','OTHER')),
    description       TEXT,
    timestamp         TEXT NOT NULL,
    input_source      TEXT NOT NULL CHECK (input_source IN ('VOICE','MANUAL','BILL')),
    language          TEXT,
    utterance_text    TEXT,
    voice_log_id      TEXT,
    payload_hash      TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_expenses_merchant_ts ON expenses(merchant_id, timestamp);

CREATE TABLE IF NOT EXISTS expense_voids (
    expense_id TEXT PRIMARY KEY REFERENCES expenses(expense_id),
    reason     TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    ledger_entry_id       TEXT PRIMARY KEY,
    merchant_id           TEXT NOT NULL REFERENCES merchants(merchant_id),
    seq                   INTEGER NOT NULL,
    entry_type            TEXT NOT NULL CHECK (entry_type IN ('PAYMENT_IN','RECLASSIFICATION','REFUND_OUT','REVERSAL','EXPENSE','EXPENSE_VOID')),
    source_type           TEXT NOT NULL CHECK (source_type IN ('PAYMENT','EXPENSE','REFUND','REVERSAL')),
    source_id             TEXT NOT NULL,
    supersedes_entry_id   TEXT,
    amount_paise          INTEGER NOT NULL CHECK (amount_paise > 0),
    classification        TEXT CHECK (classification IN ('SALE','FAMILY','PENDING')),
    classification_source TEXT CHECK (classification_source IN ('MERCHANT_CONFIG','PAYER_MEMORY','MODEL','RULE','MERCHANT_CONFIRMED')),
    confidence            TEXT,
    expense_category      TEXT,
    effective_at          TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    prev_hash             TEXT NOT NULL,
    hash                  TEXT NOT NULL,
    UNIQUE (merchant_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_ledger_source ON ledger_entries(source_type, source_id);
CREATE INDEX IF NOT EXISTS ix_ledger_merchant_effective ON ledger_entries(merchant_id, effective_at);

CREATE TABLE IF NOT EXISTS voice_logs (
    voice_log_id  TEXT PRIMARY KEY,
    merchant_id   TEXT NOT NULL REFERENCES merchants(merchant_id),
    language      TEXT NOT NULL,
    audio_sha256  TEXT,
    transcript    TEXT,
    intent        TEXT,
    entities_json TEXT,
    outcome       TEXT CHECK (outcome IN ('SAVED','ANSWERED','CONFIRMED','CLARIFY','CANCELLED','FAILED')),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notices (
    notice_id        TEXT PRIMARY KEY,
    merchant_id      TEXT NOT NULL REFERENCES merchants(merchant_id),
    file_sha256      TEXT NOT NULL,
    fields_json      TEXT NOT NULL,
    explanation_text TEXT,
    created_at       TEXT NOT NULL
);

-- Udhari (contract section 13, flag UDHARI): a credit book beside the ledger. Never creates ledger entries.
CREATE TABLE IF NOT EXISTS tabs (
    tab_id      TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id),
    payer_id    TEXT NOT NULL REFERENCES payers(payer_id),
    created_at  TEXT NOT NULL,
    UNIQUE (merchant_id, payer_id)
);

CREATE TABLE IF NOT EXISTS tab_entries (
    tab_entry_id      TEXT PRIMARY KEY,
    tab_id            TEXT NOT NULL REFERENCES tabs(tab_id),
    merchant_id       TEXT NOT NULL REFERENCES merchants(merchant_id),
    payer_id          TEXT NOT NULL REFERENCES payers(payer_id),
    kind              TEXT NOT NULL CHECK (kind IN ('ADD','SETTLE','ADJUST')),
    amount_paise      INTEGER NOT NULL CHECK (amount_paise > 0),
    direction         INTEGER NOT NULL CHECK (direction IN (1, -1)),
    transaction_id    TEXT REFERENCES payments(transaction_id),
    client_request_id TEXT NOT NULL UNIQUE,
    input_source      TEXT NOT NULL CHECK (input_source IN ('VOICE','MANUAL','PAYMENT','SEED')),
    note              TEXT,
    language          TEXT,
    utterance_text    TEXT,
    voice_log_id      TEXT,
    payload_hash      TEXT NOT NULL,
    effective_at      TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    CHECK ((kind = 'SETTLE') = (transaction_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_tab_entries_tab ON tab_entries(tab_id, effective_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_tab_entries_settle_txn ON tab_entries(transaction_id) WHERE kind = 'SETTLE';

CREATE TABLE IF NOT EXISTS demo_state (
    merchant_id     TEXT PRIMARY KEY REFERENCES merchants(merchant_id),
    next_demo_index INTEGER NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: we issue BEGIN IMMEDIATE ourselves, so each write is one explicit transaction.
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


@contextmanager
def write_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One SQLite transaction for a whole write (domain row + ledger entry + ...).

    BEGIN IMMEDIATE takes the write lock up front, which also serializes ledger seq allocation.
    Any exception rolls everything back.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def check(db_path: Path) -> bool:
    try:
        conn = connect(db_path)
        try:
            conn.execute("SELECT 1").fetchone()
            conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()
        finally:
            conn.close()
        return True
    except sqlite3.Error:
        return False
