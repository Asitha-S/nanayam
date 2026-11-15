"""Shared paths for ml scripts. The backend package is imported exactly as uvicorn and pytest do, so
training, evaluation and the live API share one feature builder and one decision procedure."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED = REPO_ROOT / "data" / "generated"
ARTIFACTS = REPO_ROOT / "ml" / "artifacts"
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
