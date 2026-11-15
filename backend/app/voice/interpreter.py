"""POST /voice/interpret (contract section 6). Owner: Asitha.

The LLM interpreter (voice/interpret.py, Charulatha) proposes when it is available and Sarvam answers with output
that passes the VOICE_AND_NOTICE 5.2 validation. Otherwise the rule-based interpreter (voice/rules.py) decides.
The endpoint never returns a canned response: every result is read from the text. The response says which
interpreter produced it: "interpreter": "LLM" | "RULES".
"""
from __future__ import annotations

import logging
import re
import sqlite3
from datetime import timedelta

from .. import clock, money
from ..questions_text import spoken_amount
from . import rules

log = logging.getLogger(__name__)
CONFIRMED = ("SALE", "FAMILY")


def open_question(conn: sqlite3.Connection, merchant_id: str, question_id: str | None) -> rules.OpenQuestion | None:
    """The question card the utterance answers, if it exists for this merchant. For an ANSWERED question (the
    remember prompt) answered_category is the payment's current classification."""
    if not question_id:
        return None
    q = conn.execute("SELECT question_id, merchant_id, transaction_id, status FROM questions WHERE question_id = ?",
                     (question_id,)).fetchone()
    if q is None or q["merchant_id"] != merchant_id:
        return None
    answered = None
    if q["status"] == "ANSWERED":
        row = conn.execute(
            "SELECT classification FROM ledger_entries WHERE source_type = 'PAYMENT' AND source_id = ?"
            " ORDER BY seq DESC LIMIT 1", (q["transaction_id"],)).fetchone()
        answered = row["classification"] if row and row["classification"] in CONFIRMED else None
    return rules.OpenQuestion(q["question_id"], answered)


def _llm(text: str, language: str, merchant_id: str, question: rules.OpenQuestion | None) -> dict | None:
    """Charulatha's LLM interpreter, when present and successful (status SUCCESS = Sarvam answered and her 5.2
    checks passed). Anything else (missing module, Sarvam unreachable or cache miss, junk output) -> None."""
    try:
        from .interpret import interpret_utterance
    except ImportError:
        return None
    try:
        out = interpret_utterance(text, language=language, merchant_id=merchant_id,
                                  open_question_id=question.question_id if question else None)
    except Exception as exc:  # the rules take over; never fail the request because the LLM path did
        log.info("LLM interpreter unavailable (%s); using rules", type(exc).__name__)
        return None
    return out if isinstance(out, dict) and out.get("status") == "SUCCESS" else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").casefold())


def _reading_from_llm(p: dict, text: str, question: rules.OpenQuestion | None) -> rules.Reading:
    """The LLM proposal, held to the same deterministic checks as the rules (5.2)."""
    today = clock.today()
    day = today - timedelta(days=1) if p.get("day") == "yesterday" else today
    intent = p.get("intent")
    if intent == "CONFIRM_TRANSACTION":
        if question is None:  # 5.2: CONFIRM without an open question is UNKNOWN
            return rules.Reading("UNKNOWN", day=day, needs_clarification=True, clarification_key="not_understood")
        cc = p.get("confirmed_category")
        fam, sale = rules.matches(text, "FAMILY"), rules.matches(text, "SALE")
        keyword = "FAMILY" if fam and not sale else "SALE" if sale and not fam else None
        if cc not in CONFIRMED or (keyword and keyword != cc):  # 5.2: must agree with the keyword match
            return rules.Reading("CONFIRM_TRANSACTION", day=day, needs_clarification=True,
                                 clarification_key="clarify_category", notes=["LLM category disagrees with the words"])
        return rules.Reading("CONFIRM_TRANSACTION", day=day, confirmed_category=cc, remember_payer=bool(p.get("remember_payer")))
    if intent == "ASK_DAILY_PROFIT":
        return rules.Reading("ASK_DAILY_PROFIT", day=day)
    if intent == "LOG_EXPENSE":
        span, rupees = p.get("amount_text_span") or "", p.get("amount_rupees")
        category = p.get("category") if p.get("category") in rules.EXPENSE_CATEGORIES else "OTHER"
        try:
            ok = bool(span) and _norm(span) in _norm(text) and rules.parse_amount(span) == rupees \
                and rules.MIN_RUPEES <= rupees <= rules.MAX_RUPEES
        except (ValueError, TypeError):
            ok = False
        if not ok:
            return rules.Reading("LOG_EXPENSE", category=category, description=p.get("description") or "", day=day,
                                 needs_clarification=True, clarification_key="clarify_amount")
        return rules.Reading("LOG_EXPENSE", amount_span=span, amount_rupees=rupees, category=category,
                             description=p.get("description") or "", day=day)
    return rules.Reading("UNKNOWN", day=day, needs_clarification=True, clarification_key="not_understood")


def _response(r: rules.Reading, text: str, language: str, interpreter: str, from_cache: bool) -> dict:
    t = rules.TEXTS.get(language, rules.TEXTS["ta"])
    entities: dict = {}
    confirmation = None
    if r.intent == "LOG_EXPENSE":
        paise = r.amount_rupees * 100 if (r.amount_rupees is not None and not r.needs_clarification) else None
        entities = {"amount_paise": paise, "amount_display": money.display(paise) if paise is not None else None,
                    "category": r.category, "description": r.description, "date": r.day.isoformat(),
                    "confirmed_category": None}
        if paise is not None:
            word = t["categories"].get(r.category, t["categories"]["OTHER"])
            confirmation = t["expense_confirm"].format(amount=spoken_amount(paise, language), category=word,
                                                       description=r.description or word)
    elif r.intent == "ASK_DAILY_PROFIT":
        entities = {"date": r.day.isoformat()}
    elif r.intent == "CONFIRM_TRANSACTION":
        entities = {"confirmed_category": r.confirmed_category, "remember_payer": r.remember_payer}
    return {
        "intent": r.intent,
        "entities": entities,
        "needs_clarification": r.needs_clarification,
        "clarification_text": t[r.clarification_key] if r.clarification_key else None,
        "confirmation_text": confirmation,
        "validation": {
            "amount_found_in_text": bool(r.amount_span) and _norm(r.amount_span) in _norm(text),
            "category_valid": r.category in rules.EXPENSE_CATEGORIES if r.intent == "LOG_EXPENSE" else True,
        },
        "from_cache": from_cache,
        "interpreter": interpreter,
    }


def interpret(conn: sqlite3.Connection, *, merchant_id: str, language: str, text: str,
              open_question_id: str | None) -> dict:
    question = open_question(conn, merchant_id, open_question_id)
    proposal = _llm(text, language, merchant_id, question)
    if proposal is not None:
        return _response(_reading_from_llm(proposal, text, question), text, language, "LLM",
                         bool(proposal.get("from_cache", False)))
    reading = rules.interpret(text, today=clock.today(), open_question=question)
    return _response(reading, text, language, "RULES", False)
