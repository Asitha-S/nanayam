"""Expenses (contract section 5). REAL: POST /expenses. STUB (fixtures): list, void."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Response

from ..deps import get_conn
from ..schemas import ExpenseCategory, ExpenseIn, ExpenseVoidIn
from ..services import expenses as svc
from ..stubs import fixture, require_merchant, require_merchant_422

router = APIRouter(tags=["expenses"])


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    status, out = svc.create_expense(conn, body)
    response.status_code = status
    return out


@router.get("/merchants/{merchant_id}/expenses")
def list_expenses(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: ExpenseCategory | None = None,
    include_voided: bool = False,
):
    require_merchant(merchant_id)  # STUB
    return fixture("expenses_list_M001_2026-11-15")


@router.post("/expenses/{expense_id}/void", status_code=201)
def void_expense(expense_id: str, body: ExpenseVoidIn):
    require_merchant_422(body.merchant_id)  # STUB
    return fixture("expense_void")
