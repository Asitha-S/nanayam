"""/demo/* (contract section 1). Mounted only when ENABLE_DEMO_TOOLS=true, else every path is 404. All real."""
import sqlite3

from fastapi import APIRouter, Body, Depends, Query

from .. import repo
from ..config import get_settings
from ..demo import service
from ..deps import get_conn
from ..schemas import DemoResetIn, MerchantRef, TamperIn

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(body: DemoResetIn | None = Body(default=None)):
    return service.reset(get_settings().db_path)


@router.post("/next-payment", status_code=201)
def next_payment(body: MerchantRef, conn: sqlite3.Connection = Depends(get_conn)):
    return service.next_payment(conn, body.merchant_id)


@router.get("/script")
def script(merchant_id: str = Query(...), conn: sqlite3.Connection = Depends(get_conn)):
    return service.script_view(conn, merchant_id)


@router.post("/tamper")
def tamper(body: TamperIn, conn: sqlite3.Connection = Depends(get_conn)):
    from ..demo.tamper import tamper as do_tamper  # the only import of demo/tamper.py, kept inside the route

    repo.require_merchant_in_body(conn, body.merchant_id)
    do_tamper(conn, body.merchant_id, body.ledger_entry_id)
    return {"tampered": True}
