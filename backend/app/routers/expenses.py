"""Expenses (contract section 5). STUB: fixtures, but the time window is already enforced."""
from datetime import date, timedelta

from fastapi import APIRouter

from .. import clock, errors
from ..schemas import ExpenseCategory, ExpenseIn, ExpenseVoidIn
from ..stubs import fixture, require_merchant, require_merchant_422

router = APIRouter(tags=["expenses"])

MAX_DAYS_BACK = 7


def check_expense_time(timestamp: str, prev_created_at=None) -> None:
    """Not in the future (vs the effective now) and not more than 7 days back."""
    ts = clock.parse(timestamp)
    now = clock.effective_now(prev_created_at)
    if ts > now:
        raise errors.validation_error("Expense timestamp is in the future", field="timestamp")
    if ts < now - timedelta(days=MAX_DAYS_BACK):
        raise errors.validation_error("Expense timestamp is more than 7 days back", field="timestamp")


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn):
    require_merchant_422(body.merchant_id)
    check_expense_time(body.timestamp)
    return fixture("expenses_post")


@router.get("/merchants/{merchant_id}/expenses")
def list_expenses(
    merchant_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: ExpenseCategory | None = None,
    include_voided: bool = False,
):
    require_merchant(merchant_id)
    return fixture("expenses_list_M001_2026-11-15")


@router.post("/expenses/{expense_id}/void", status_code=201)
def void_expense(expense_id: str, body: ExpenseVoidIn):
    require_merchant_422(body.merchant_id)
    return fixture("expense_void")
