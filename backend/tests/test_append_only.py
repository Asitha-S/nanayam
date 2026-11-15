"""DATA_AND_LOGIC 1.2: no UPDATE/DELETE on append-only tables anywhere in the backend,
except backend/app/demo/tamper.py (only reachable through /demo/tamper)."""
import re
from pathlib import Path

from app.db import APPEND_ONLY_TABLES

APP_DIR = Path(__file__).resolve().parents[1] / "app"
EXCLUDED = {APP_DIR / "demo" / "tamper.py"}

PATTERN = re.compile(
    r"\b(UPDATE|DELETE\s+FROM|REPLACE\s+INTO|INSERT\s+OR\s+REPLACE\s+INTO)\s+(" + "|".join(APPEND_ONLY_TABLES) + r")\b",
    re.IGNORECASE,
)


def test_no_update_or_delete_on_append_only_tables():
    hits = []
    for path in APP_DIR.rglob("*.py"):
        if path in EXCLUDED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if PATTERN.search(line):
                hits.append(f"{path.relative_to(APP_DIR)}:{n}: {line.strip()}")
    assert hits == []


def test_pattern_catches_violations():
    assert PATTERN.search("UPDATE ledger_entries SET amount_paise = 1")
    assert PATTERN.search("delete from expenses where 1")
    assert not PATTERN.search("UPDATE questions SET status = 'ANSWERED'")
