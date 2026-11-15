"""Merchants (contract section 2). STUB: fixtures."""
from fastapi import APIRouter

from ..schemas import MerchantUpdateIn
from ..stubs import fixture, require_merchant

router = APIRouter(tags=["merchants"])

# Stub defaults for merchants other than M001 (values from DATA_AND_LOGIC section 3.1).
_DEFAULTS = {"city": "Chennai", "family_payers": [], "created_at": "2026-08-01T05:00:00+05:30"}


@router.get("/merchants")
def list_merchants():
    return fixture("merchants")


def _merchant(merchant_id: str) -> dict:
    if merchant_id == "M001":
        return fixture("merchant_M001")
    summary = next(m for m in fixture("merchants")["merchants"] if m["merchant_id"] == merchant_id)
    return {
        "merchant_id": summary["merchant_id"],
        "display_name": summary["display_name"],
        "owner_name": summary["owner_name"],
        "city": _DEFAULTS["city"],
        "business_category": summary["business_category"],
        "preferred_language": summary["preferred_language"],
        "family_payers": list(_DEFAULTS["family_payers"]),
        "created_at": _DEFAULTS["created_at"],
    }


@router.get("/merchants/{merchant_id}")
def get_merchant(merchant_id: str):
    require_merchant(merchant_id)
    return _merchant(merchant_id)


@router.put("/merchants/{merchant_id}")
def update_merchant(merchant_id: str, body: MerchantUpdateIn):
    require_merchant(merchant_id)
    return _merchant(merchant_id)
