"""/demo/* (contract section 1). Mounted only when ENABLE_DEMO_TOOLS=true, else every path is 404.

STUB: in-memory state. Real version restores data/demo/seed.db and injects through POST /payments.
"""
from fastapi import APIRouter, Body, Query, Request

from .. import errors
from ..schemas import DemoResetIn, MerchantRef, TamperIn
from ..stubs import fixture, require_merchant, require_merchant_422

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_SCRIPT_LENGTH = {"M001": 15, "M002": 11}


@router.post("/reset")
def reset(request: Request, body: DemoResetIn | None = Body(default=None)):
    request.app.state.demo.reset()
    return fixture("demo_reset")


@router.post("/next-payment", status_code=201)
def next_payment(request: Request, body: MerchantRef):
    require_merchant_422(body.merchant_id)
    total = DEMO_SCRIPT_LENGTH.get(body.merchant_id, 0)
    state = request.app.state.demo
    index = state.next_index.get(body.merchant_id, 1)
    if index > total:
        raise errors.invalid_state("Demo script finished for this merchant", merchant_id=body.merchant_id)
    state.next_index[body.merchant_id] = index + 1
    # Stub: the last scripted payment is the ASK one; every earlier one returns the AUTO fixture.
    out = fixture("demo_next_payment_015" if index == total else "demo_next_payment_001")
    out["demo_index"] = index
    out["demo_remaining"] = total - index
    return out


@router.get("/script")
def script(merchant_id: str = Query(...)):
    require_merchant(merchant_id)
    return fixture("demo_script_M001")


@router.post("/tamper")
def tamper(request: Request, body: TamperIn):
    require_merchant_422(body.merchant_id)
    request.app.state.demo.tampered = True
    return {"tampered": True}
