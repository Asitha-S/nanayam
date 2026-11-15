"""Merchants (contract section 2). All real."""
import sqlite3

from fastapi import APIRouter, Depends

from ..deps import get_conn
from ..schemas import MerchantUpdateIn
from ..services import insights as svc

router = APIRouter(tags=["merchants"])


@router.get("/merchants")
def list_merchants(conn: sqlite3.Connection = Depends(get_conn)):
    return svc.list_merchants(conn)


@router.get("/merchants/{merchant_id}")
def get_merchant(merchant_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.merchant_detail(conn, merchant_id)


@router.put("/merchants/{merchant_id}")
def update_merchant(merchant_id: str, body: MerchantUpdateIn, conn: sqlite3.Connection = Depends(get_conn)):
    return svc.update_merchant(conn, merchant_id, body)
