from fastapi import APIRouter, Request

from .. import db
from ..classifier.decide import active_model_version, threshold
from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    settings = get_settings()
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "demo_date": settings.demo_date.isoformat(),
        "db": "ok" if db.check(settings.db_path) else "error",
        "model_version": active_model_version(),
        "threshold": threshold(),
        "demo_tools": settings.enable_demo_tools,
        "tampered": request.app.state.demo.tampered,
    }
