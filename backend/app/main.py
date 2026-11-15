"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
(--host 0.0.0.0 so phones on the same Wi-Fi/hotspot can reach it for the /pay page)."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, errors
from .config import get_settings
from .routers import demo, expenses, export, health, insights, ledger, merchants, payments, voice, udhari
from .udhari import seed as udhari_seed

API_PREFIX = "/api"
PAY_PAGE_GAP_S = 2.0


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db(settings.db_path)
        if settings.udhari:  # the demo tabs (contract section 13); nothing when the flag is off
            udhari_seed.ensure_path(settings.db_path)
        yield

    app = FastAPI(title="Naanayam API", version="1.1", lifespan=lifespan)
    errors.install_handlers(app)

    # The customer /pay page (header X-Naanayam-Client: pay-page) may send one payment every 2 s per device, so a
    # phone can't flood the demo. Added before CORS so the 429 still carries CORS headers.
    last_pay: dict[str, float] = {}

    @app.middleware("http")
    async def pay_page_rate_limit(request: Request, call_next):
        if (request.method == "POST" and request.url.path == f"{API_PREFIX}/payments"
                and request.headers.get("x-naanayam-client") == "pay-page"):
            who = request.client.host if request.client else "?"
            now = time.monotonic()
            wait = PAY_PAGE_GAP_S - (now - last_pay.get(who, -1e9))
            if wait > 0:
                e = errors.rate_limited("One payment every 2 seconds from the same phone. Try again in a moment.",
                                        retry_after_s=round(wait, 1))
                return JSONResponse(status_code=e.status, content=errors.error_body(e.code, e.message, e.details))
            last_pay[who] = now
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        # the laptop itself and phones on the same LAN (private address ranges), any dev/preview port
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                           r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, merchants, payments, expenses, voice, ledger, insights, export, udhari):
        app.include_router(module.router, prefix=API_PREFIX)
    if settings.enable_demo_tools:  # otherwise /api/demo/* falls through to 404 NOT_FOUND
        app.include_router(demo.router, prefix=API_PREFIX)
    return app


logging.basicConfig(level=logging.INFO)
app = create_app()
