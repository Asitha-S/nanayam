"""Udhari endpoints (contract section 13). 404 while the UDHARI flag is off."""
import sqlite3

from fastapi import APIRouter, Depends, Response

from ..deps import get_conn
from ..schemas import TabAddIn, TabSettleIn, VoiceLanguage
from ..udhari import service as svc

router = APIRouter(tags=["udhari"])


@router.get("/merchants/{merchant_id}/tabs")
def list_tabs(merchant_id: str, language: VoiceLanguage | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.list_tabs(conn, merchant_id, language)


@router.post("/tabs/{payer_id}/add", status_code=201)
def add(payer_id: str, body: TabAddIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.add(conn, payer_id, body)
    response.status_code = status
    return out


@router.post("/tabs/{payer_id}/settle", status_code=201)
def settle(payer_id: str, body: TabSettleIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.settle(conn, payer_id, body)
    response.status_code = status
    return out
