"""POST /voice/interpret (contract section 6). Owner: Asitha.

The rule-based interpreter (voice/rules.py) reads first: it is instant and tested on everyday Tamil, Tanglish, Telugu
and English sentences. Only a sentence the rules can't read (UNKNOWN) goes to the LLM interpreter (voice/interpret.py,
Charulatha), whose answer must pass the VOICE_AND_NOTICE 5.2 validation.
The endpoint never returns a canned response: every result is read from the text. The response says which
interpreter produced it: "interpreter": "LLM" | "RULES".
The LLM gets LLM_BUDGET_S: a slow Sarvam chat call (8 s timeout plus a retry) never holds the merchant waiting; the rules
answer instead, and the late LLM answer still lands in the Sarvam cache for next time.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta

from .. import clock, money
from ..questions_text import spoken_amount
from ..udhari import service as udhari
from ..udhari import texts as udhari_texts
from . import rules

log = logging.getLogger(__name__)
CONFIRMED = ("SALE", "FAMILY")
LLM_BUDGET_S = 3.5
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-interpret")


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


def _llm_within_budget(text: str, language: str, merchant_id: str, question: rules.OpenQuestion | None) -> dict | None:
    """_llm, but never longer than LLM_BUDGET_S (the call keeps running in the background and fills the cache)."""
    future = _POOL.submit(_llm, text, language, merchant_id, question)
    try:
        return future.result(timeout=LLM_BUDGET_S)
    except FutureTimeout:
        log.info("LLM interpreter took over %.1f s; using rules", LLM_BUDGET_S)
        return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").casefold())


def _reading_from_llm(p: dict, text: str, question: rules.OpenQuestion | None) -> rules.Reading | None:
    """The LLM proposal, held to the same deterministic checks as the rules (5.2). None: the proposal is not used
    (it gave up, or its intent contradicts the words) and the rules read the text instead."""
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
        # a rupee figure and no profit word is not a profit question ("வீட்டு செலவு 6000 ரூபாய்")
        if rules.find_amount(text) and not rules.matches(text, "PROFIT"):
            return None
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
    return None  # the LLM did not understand it: the rules may still read it


def _udhari_response(conn: sqlite3.Connection, merchant_id: str, r: rules.Reading, text: str, language: str) -> dict:
    """ADD_CREDIT / ASK_DUES (UDHARI flag, contract section 13). The payer is matched against the merchant's tab payers
    and regular customers; nothing is written here."""
    base = {"needs_clarification": False, "clarification_text": None, "confirmation_text": None, "from_cache": False,
            "interpreter": "RULES", "validation": {"amount_found_in_text": False, "category_valid": True}}
    if r.intent == "ASK_DUES":
        return {**base, "intent": "ASK_DUES", "entities": {"date": r.day.isoformat()}}
    best, candidates = udhari.payer_candidates(conn, merchant_id, r.payer_heard)
    paise = r.amount_rupees * 100 if r.amount_rupees is not None else None
    t = rules.TEXTS.get(language, rules.TEXTS["ta"])
    clarify = None
    if r.clarification_key == "clarify_amount":
        clarify = t["clarify_amount"]
    elif r.clarification_key == "clarify_payer":
        clarify = udhari_texts.clarify_payer(language)
    name = best["payer_name"] if best else r.payer_heard
    return {
        **base,
        "intent": "ADD_CREDIT",
        "entities": {"payer_heard": r.payer_heard, "payer_id": best["payer_id"] if best else None,
                     "payer_name": best["payer_name"] if best else None, "payer_candidates": candidates,
                     "amount_paise": paise, "amount_display": money.display(paise) if paise is not None else None,
                     "date": r.day.isoformat()},
        "needs_clarification": r.needs_clarification,
        "clarification_text": clarify,
        "confirmation_text": udhari_texts.credit_confirm(language, name, paise) if (paise is not None and name) else None,
        "validation": {"amount_found_in_text": bool(r.amount_span) and _norm(r.amount_span) in _norm(text),
                       "category_valid": True},
    }


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
    reading = rules.interpret(text, today=clock.today(), open_question=question, udhari=udhari.enabled())
    if reading.intent in ("ADD_CREDIT", "ASK_DUES"):
        return _udhari_response(conn, merchant_id, reading, text, language)
    if reading.intent != "UNKNOWN":
        return _response(reading, text, language, "RULES", False)
    proposal = _llm_within_budget(text, language, merchant_id, question)
    if proposal is not None:
        llm_reading = _reading_from_llm(proposal, text, question)
        if llm_reading is not None:
            return _response(llm_reading, text, language, "LLM", bool(proposal.get("from_cache", False)))
    return _response(reading, text, language, "RULES", False)
