"""/demo/* (contract section 1). Mounted only when ENABLE_DEMO_TOOLS=true, else every path is 404. All real.
Live mode (demo/live.py): /demo/live-payment, /demo/pay-options, /demo/network."""
import sqlite3

from fastapi import APIRouter, Body, Depends, Query

from .. import repo
from ..udhari import seed as udhari_seed
from ..config import get_settings
from ..demo import live, service
from ..deps import get_conn
from ..schemas import DemoResetIn, MerchantRef, TamperIn

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset(body: DemoResetIn | None = Body(default=None)):
    out = service.reset(get_settings().db_path)
    udhari_seed.ensure_path(get_settings().db_path)  # the demo tabs come back with the seed (UDHARI on only)
    return out


@router.post("/next-payment", status_code=201)
def next_payment(body: MerchantRef, conn: sqlite3.Connection = Depends(get_conn)):
    return service.next_payment(conn, body.merchant_id)


@router.get("/script")
def script(merchant_id: str = Query(...), conn: sqlite3.Connection = Depends(get_conn)):
    return service.script_view(conn, merchant_id)


@router.post("/live-payment", status_code=201)
def live_payment(body: MerchantRef, conn: sqlite3.Connection = Depends(get_conn)):
    """One payment sampled from the merchant's own payers, sent through the POST /payments path at the current time."""
    repo.require_merchant_in_body(conn, body.merchant_id)
    status, payload = live.live_payment(conn, body.merchant_id)
    return payload


@router.get("/pay-options")
def pay_options(merchant_id: str = Query(...), conn: sqlite3.Connection = Depends(get_conn)):
    """Who can pay this merchant on the customer /pay page (no classification hints)."""
    return live.pay_options(conn, merchant_id)


@router.get("/network")
def network():
    """This laptop's LAN addresses, for the QR code that opens /pay on a phone."""
    return {"lan_ips": live.lan_addresses()}


@router.post("/tamper")
def tamper(body: TamperIn, conn: sqlite3.Connection = Depends(get_conn)):
    from ..demo.tamper import tamper as do_tamper  # the only import of demo/tamper.py, kept inside the route

    repo.require_merchant_in_body(conn, body.merchant_id)
    do_tamper(conn, body.merchant_id, body.ledger_entry_id)
    return {"tampered": True}
