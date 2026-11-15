"""Expenses (contract section 5). All real."""
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Response

from .. import periods, repo
from ..deps import get_conn
from ..schemas import ExpenseCategory, ExpenseIn, ExpenseVoidIn
from ..services import expenses as svc

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
    conn: sqlite3.Connection = Depends(get_conn),
):
    start, end = periods.resolve(start_date, end_date)
    return svc.list_expenses(conn, merchant_id, start, end, category, include_voided)


@router.post("/expenses/{expense_id}/void", status_code=201)
def void_expense(expense_id: str, body: ExpenseVoidIn, conn: sqlite3.Connection = Depends(get_conn)):
    repo.require_merchant_in_body(conn, body.merchant_id)
    _, out = svc.void_expense(conn, expense_id, body)
    return out
