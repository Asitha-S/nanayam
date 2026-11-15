from fastapi import APIRouter, Request

from .. import db
from ..classifier.threshold import current_model, effective_threshold
from ..config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request):
    settings = get_settings()
    model = current_model()
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "demo_date": settings.demo_date.isoformat(),
        "db": "ok" if db.check(settings.db_path) else "error",
        "model_version": model.model_version if model else None,
        "threshold": effective_threshold(model.threshold if model else None, settings.conf_threshold),
        "demo_tools": settings.enable_demo_tools,
        "tampered": request.app.state.demo.tampered,
    }
