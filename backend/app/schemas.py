"""Request bodies (contract sections 1-9). Enum strings are exact. Unknown fields are rejected.

The backend revalidates everything, whatever the frontend already checked (PROJECT rule 18).
Checks that need the clock or the database (expense time window, merchant exists, question
binding) happen in the routers/services, not here.
"""
from __future__ import annotations

from datetime import date as Date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Language = Literal["ta", "te", "en"]
VoiceLanguage = Literal["ta", "te"]
BusinessCategory = Literal["VEGETABLES", "FRUITS", "FLOWERS", "TEA_STALL", "MIXED_KIRANA"]
PaymentType = Literal["P2M", "P2P"]
PayerVpaKind = Literal["PERSONAL", "BUSINESS"]
Classification = Literal["SALE", "FAMILY", "PENDING"]
ConfirmableCategory = Literal["SALE", "FAMILY"]
EntryType = Literal["PAYMENT_IN", "RECLASSIFICATION", "REFUND_OUT", "REVERSAL", "EXPENSE", "EXPENSE_VOID"]
ExpenseCategory = Literal["STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT", "WAGES", "UTILITIES", "OTHER"]
InputSource = Literal["VOICE", "MANUAL", "BILL"]
ConfirmationChannel = Literal["TAP", "VOICE"]
QuestionStatus = Literal["OPEN", "ANSWERED"]
Intent = Literal["LOG_EXPENSE", "ASK_DAILY_PROFIT", "CONFIRM_TRANSACTION", "UNKNOWN"]

EXPENSE_MIN_PAISE = 100  # ₹1
EXPENSE_MAX_PAISE = 50_000_000  # ₹5,00,000


def _iso_with_offset(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be an ISO 8601 timestamp like 2026-11-15T19:42:10+05:30") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamp must include an offset (+05:30)")
    return value


Timestamp = Annotated[str, AfterValidator(_iso_with_offset)]
Paise = Annotated[int, Field(strict=True, gt=0)]
NonEmpty = Annotated[str, Field(min_length=1)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- demo -------------------------------------------------------------------
class DemoResetIn(Strict):
    pass


class MerchantRef(Strict):
    merchant_id: NonEmpty


class TamperIn(Strict):
    merchant_id: NonEmpty
    ledger_entry_id: NonEmpty


# --- merchants --------------------------------------------------------------
class MerchantUpdateIn(Strict):
    preferred_language: Language | None = None
    business_category: BusinessCategory | None = None
    family_payer_ids: list[NonEmpty] | None = None


# --- payments ---------------------------------------------------------------
class PaymentIn(Strict):
    transaction_id: NonEmpty
    merchant_id: NonEmpty
    payer_id: NonEmpty
    payer_name: NonEmpty
    payer_vpa_kind: PayerVpaKind
    amount_paise: Paise
    payment_type: PaymentType
    timestamp: Timestamp
    description: str | None = None


class RefundIn(Strict):
    refund_id: NonEmpty
    amount_paise: Paise
    timestamp: Timestamp
    reason: str | None = None


class ReversalIn(Strict):
    timestamp: Timestamp
    reason: str | None = None


class ConfirmIn(Strict):
    merchant_id: NonEmpty
    question_id: str | None = None
    confirmed_category: ConfirmableCategory
    channel: ConfirmationChannel
    utterance_text: str | None = None
    remember_payer: bool = False

    @model_validator(mode="after")
    def _remember_only_family(self):
        if self.remember_payer and self.confirmed_category != "FAMILY":
            raise ValueError("remember_payer is only allowed with confirmed_category FAMILY")
        return self


class PreviewIn(Strict):
    merchant_id: NonEmpty
    payer_id: NonEmpty
    amount_paise: Paise
    payment_type: PaymentType
    timestamp: Timestamp


# --- expenses ---------------------------------------------------------------
class ExpenseIn(Strict):
    client_request_id: UUID
    merchant_id: NonEmpty
    amount_paise: Annotated[int, Field(strict=True, ge=EXPENSE_MIN_PAISE, le=EXPENSE_MAX_PAISE)]
    category: ExpenseCategory
    description: str | None = None
    timestamp: Timestamp
    input_source: InputSource
    language: Language | None = None
    utterance_text: str | None = None
    voice_log_id: str | None = None


class ExpenseVoidIn(Strict):
    merchant_id: NonEmpty
    reason: str | None = None


# --- voice ------------------------------------------------------------------
class InterpretIn(Strict):
    merchant_id: NonEmpty
    language: Language
    text: NonEmpty
    voice_log_id: str | None = None
    open_question_id: str | None = None


class AnswerIn(Strict):
    merchant_id: NonEmpty
    language: Language
    intent: Intent
    date: Date | None = None


class SpeakIn(Strict):
    merchant_id: NonEmpty
    language: Language
    text: NonEmpty
