"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, errors
from .config import get_settings
from .routers import demo, expenses, export, health, insights, ledger, merchants, payments, voice
from .stubs import DemoState

API_PREFIX = "/api"


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db(settings.db_path)
        yield

    app = FastAPI(title="Naanayam API", version="1.1", lifespan=lifespan)
    app.state.demo = DemoState()
    errors.install_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, merchants, payments, expenses, voice, ledger, insights, export):
        app.include_router(module.router, prefix=API_PREFIX)
    if settings.enable_demo_tools:  # otherwise /api/demo/* falls through to 404 NOT_FOUND
        app.include_router(demo.router, prefix=API_PREFIX)
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
