"""Vercel entry point: the FastAPI app in backend/app, served as one Python function for every /api/* path.

Vercel's file system is read-only except /tmp, so the working database, the Sarvam dev cache and the logs live in
/tmp/naanayam. A new instance starts from the committed demo seed (data/demo/seed.db), exactly like POST /demo/reset,
and keeps its state for as long as the instance lives. The settings below are defaults: anything set in the Vercel
project's environment variables wins. SARVAM_API_KEY is set there, never here.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = Path("/tmp/naanayam")

for key, value in {
    "DB_PATH": str(WORK / "naanayam.db"),
    "LOGS_DIR": str(WORK / "logs"),
    "SARVAM_CACHE_ROOT": str(WORK / "cache"),
    "SARVAM_CACHE_DIR": "dev",
    "DEMO_MODE": "cache_first",
    "ENABLE_DEMO_TOOLS": "true",
    "UDHARI": "true",
}.items():
    os.environ.setdefault(key, value)

# The committed demo cache is read-only: link it into the writable cache root; new responses go to sarvam_dev there.
cache_root = Path(os.environ["SARVAM_CACHE_ROOT"])
cache_root.mkdir(parents=True, exist_ok=True)
demo_cache = cache_root / "sarvam_demo"
if not demo_cache.exists():
    try:
        demo_cache.symlink_to(ROOT / "cache" / "sarvam_demo", target_is_directory=True)
    except OSError:
        shutil.copytree(ROOT / "cache" / "sarvam_demo", demo_cache)

# LightGBM's Linux wheel needs the system libgomp.so.1, which the serverless runtime may not have. Load the bundled
# copy (see _native/README.md) before anything imports lightgbm; the system one wins when it exists.
if sys.platform.startswith("linux"):
    try:
        ctypes.CDLL("libgomp.so.1", mode=ctypes.RTLD_GLOBAL)
    except OSError:
        ctypes.CDLL(str(HERE / "_native" / "libgomp.so.1"), mode=ctypes.RTLD_GLOBAL)

sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.demo import service as demo_service  # noqa: E402
from app.udhari import seed as udhari_seed  # noqa: E402

settings = get_settings()
if not settings.db_path.exists():
    demo_service.reset(settings.db_path)
db.init_db(settings.db_path)
if settings.udhari:
    udhari_seed.ensure_path(settings.db_path)

from app.main import app  # noqa: E402,F401  (Vercel serves this ASGI app)
