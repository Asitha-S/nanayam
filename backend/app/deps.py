"""Per-request database connection."""
from typing import Iterator

import sqlite3

from . import db
from .config import get_settings


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()
