"""Settings from environment variables (PROJECT.md section 6).

`.env` at the repository root is loaded once; real environment variables win over it.
Call `get_settings.cache_clear()` after changing the environment (tests do this).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "contract" / "fixtures"
DEMO_DATA_DIR = REPO_ROOT / "data" / "demo"

load_dotenv(REPO_ROOT / ".env", override=False)

DEMO_MODES = ("cache_only", "cache_first", "live")


@dataclass(frozen=True)
class Settings:
    sarvam_api_key: str | None
    demo_mode: str
    demo_date: date
    db_path: Path
    conf_threshold: float
    enable_demo_tools: bool
    sarvam_cache_dir: str  # "dev" or "demo": where new Sarvam responses are written
    sarvam_person: str
    cache_root: Path
    logs_dir: Path
    demo_seed_db: Path


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else REPO_ROOT / p


@lru_cache
def get_settings() -> Settings:
    demo_mode = os.getenv("DEMO_MODE", "cache_first").strip()
    if demo_mode not in DEMO_MODES:
        raise ValueError(f"DEMO_MODE must be one of {DEMO_MODES}, got {demo_mode!r}")
    cache_dir = os.getenv("SARVAM_CACHE_DIR", "dev").strip()
    if cache_dir not in ("dev", "demo"):
        raise ValueError(f"SARVAM_CACHE_DIR must be 'dev' or 'demo', got {cache_dir!r}")
    return Settings(
        sarvam_api_key=os.getenv("SARVAM_API_KEY") or None,
        demo_mode=demo_mode,
        demo_date=date.fromisoformat(os.getenv("DEMO_DATE", "2026-11-15").strip()),
        db_path=_path(os.getenv("DB_PATH", "backend/naanayam.db")),
        conf_threshold=float(os.getenv("CONF_THRESHOLD", "0.90")),
        enable_demo_tools=_bool(os.getenv("ENABLE_DEMO_TOOLS", "false")),
        sarvam_cache_dir=cache_dir,
        sarvam_person=os.getenv("SARVAM_PERSON", "").strip() or "unknown",
        cache_root=_path(os.getenv("SARVAM_CACHE_ROOT", "cache")),
        logs_dir=_path(os.getenv("LOGS_DIR", "logs")),
        demo_seed_db=_path(os.getenv("DEMO_SEED_DB", "data/demo/seed.db")),
    )
