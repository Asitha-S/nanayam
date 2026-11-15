"""Fixture stubs (BUILD_PLAN section 1, "Unblocking rule").

Until real logic lands, endpoints return the matching file from contract/fixtures/. Stubs are
deliberately simple: they always return M001-shaped data for any known merchant. Real
implementations replace them behind the same routes.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

from . import errors
from .config import FIXTURES_DIR


@lru_cache
def _read(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fixture(name: str) -> dict:
    """A fresh copy of contract/fixtures/{name}.json."""
    return copy.deepcopy(_read(name))


def known_merchant_ids() -> list[str]:
    return [m["merchant_id"] for m in _read("merchants")["merchants"]]


def require_merchant(merchant_id: str) -> None:
    if merchant_id not in known_merchant_ids():
        raise errors.not_found(f"Unknown merchant {merchant_id}", merchant_id=merchant_id)


def require_merchant_422(merchant_id: str) -> None:
    """Writes report an unknown merchant in the body as 422 (contract section 3)."""
    if merchant_id not in known_merchant_ids():
        raise errors.validation_error(f"Unknown merchant {merchant_id}", field="merchant_id")


class DemoState:
    """In-memory demo state for the stub phase (next scripted payment, tamper flag)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.next_index: dict[str, int] = {}
        self.tampered = False
