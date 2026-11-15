from fastapi import APIRouter

from .. import clock, db
from ..classifier.decide import active_model_version, threshold
from ..config import get_settings
from ..demo.service import is_tampered

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    settings = get_settings()
    db_ok = db.check(settings.db_path)
    tampered = False
    if db_ok:
        conn = db.connect(settings.db_path)
        try:
            tampered = is_tampered(conn)
        finally:
            conn.close()
    return {
        "status": "ok",
        "now": clock.iso(clock.now()),
        "demo_mode": settings.demo_mode,
        "demo_date": settings.demo_date.isoformat(),
        "db": "ok" if db_ok else "error",
        "model_version": active_model_version(),
        "threshold": threshold(),
        "demo_tools": settings.enable_demo_tools,
        "tampered": tampered,
        "features": {"udhari": settings.udhari},
    }
