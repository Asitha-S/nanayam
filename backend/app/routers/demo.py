"""/demo/* (contract section 1). Mounted only when ENABLE_DEMO_TOOLS=true, else every path is 404.

REAL: reset (from data/demo/seed.db), next-payment and script (from data/demo/*_demo_day.json).
STUB: tamper (in-memory flag; the real SQLite edit lives in demo/tamper.py with P3).
"""
import sqlite3

from fastapi import APIRouter, Body, Depends, Query, Request

from ..config import get_settings
from ..demo import service
from ..deps import get_conn
from ..schemas import DemoResetIn, MerchantRef, TamperIn
from ..stubs import require_merchant_422

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(request: Request, body: DemoResetIn | None = Body(default=None)):
    out = service.reset(get_settings().db_path)
    request.app.state.demo.reset()
    return out


@router.post("/next-payment", status_code=201)
def next_payment(body: MerchantRef, conn: sqlite3.Connection = Depends(get_conn)):
    return service.next_payment(conn, body.merchant_id)


@router.get("/script")
def script(merchant_id: str = Query(...), conn: sqlite3.Connection = Depends(get_conn)):
    return service.script_view(conn, merchant_id)


@router.post("/tamper")
def tamper(request: Request, body: TamperIn):
    require_merchant_422(body.merchant_id)  # STUB
    request.app.state.demo.tampered = True
    return {"tampered": True}
