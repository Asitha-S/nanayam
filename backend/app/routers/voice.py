"""Voice endpoints (contract section 6). Routers and most of backend/app/voice/ are Asitha's; the LLM interpreter
(voice/interpret.py, with amount parsing in voice/utils.py) is Charulatha's.

REAL: /voice/answer, /voice/interpret (voice/rules.py reads first; Charulatha's LLM interpreter reads what the
rules can't),
/voice/speak and /voice/transcribe (through the Sarvam client: cache and DEMO_MODE apply; a miss is 503, never a
canned answer), /payments/{id}/announcement (fixed template). Nothing here returns a fixture.
The demo-clip hash check is already real: a demo_key with the wrong bytes is a 422.
"""
import io
import sqlite3
import wave

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .. import clock, db, errors, money, repo
from ..udhari import service as udhari
from ..deps import get_conn
from ..sarvam import client as sarvam
from ..questions_text import question_text, question_text_en, spoken_amount
from ..voice import interpreter
from ..voice.answer import daily_profit
from ..schemas import AnswerIn, InterpretIn, SpeakIn, VoiceLanguage
from ..stubs import require_merchant_422

router = APIRouter(tags=["voice"])

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~30 s of 16 kHz WAV is ~1 MB; anything this big is too long


def _duration_ms(data: bytes) -> int | None:
    try:
        with wave.open(io.BytesIO(data)) as w:
            return int(w.getnframes() * 1000 / w.getframerate())
    except Exception:  # not a WAV (webm/ogg from the mic): duration unknown
        return None


@router.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: VoiceLanguage = Form(...),
    merchant_id: str = Form(...),
    demo_key: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """REAL: Sarvam STT through the client (demo clips must match their registered hash; a live recording is never
    given a scripted transcript). cache_only with an unseen recording is 503 CACHE_MISS."""
    require_merchant_422(merchant_id)
    data = await audio.read()
    if not data:
        raise errors.validation_error("Empty audio", field="audio")
    if len(data) > MAX_AUDIO_BYTES:
        raise errors.validation_error("Audio too long (max 30 s)", field="audio")
    res = await run_in_threadpool(sarvam.stt, data, language, demo_key, audio.filename or "audio.wav")
    with db.write_tx(conn):
        vl = repo.next_id(conn, "voice_logs", "voice_log_id", f"VL-{merchant_id}-")
        conn.execute("INSERT INTO voice_logs (voice_log_id, merchant_id, language, audio_sha256, transcript, created_at)"
                     " VALUES (?, ?, ?, ?, ?, ?)", (vl, merchant_id, language, res.audio_sha256, res.text, clock.iso(clock.now())))
    return {"voice_log_id": vl, "text": res.text, "language": language, "provider": "sarvam",
            "recognition_mode": res.recognition_mode, "from_cache": res.from_cache, "duration_ms": _duration_ms(data)}


# payment_announce (VOICE_AND_NOTICE 7): what the Soundbox says when money arrives. Fixed template, no LLM.
ANNOUNCE = {"ta": "{amount} வந்திருக்கு.", "te": "{amount} వచ్చాయి."}


@router.get("/payments/{transaction_id}/announcement")
def announcement(transaction_id: str, language: VoiceLanguage = Query("ta"), conn: sqlite3.Connection = Depends(get_conn)):
    """The Soundbox's words for a payment (and its question, when one is open), in the merchant's language and in
    English for a device voice without that language. Speech form of the amount from money.display."""
    p = conn.execute("SELECT p.amount_paise, p.merchant_id, py.payer_name FROM payments p JOIN payers py USING (payer_id)"
                     " WHERE p.transaction_id = ?", (transaction_id,)).fetchone()
    if p is None:
        raise errors.not_found(f"Unknown transaction {transaction_id}", transaction_id=transaction_id)
    q = conn.execute("SELECT question_id FROM questions WHERE transaction_id = ? AND status = 'OPEN'", (transaction_id,)).fetchone()
    shown = money.display(p["amount_paise"]).replace(money.RUPEE, "")
    extra = {"tab_offer": udhari.offer_for_payment(conn, transaction_id, language)} if udhari.enabled() else {}
    return {
        "transaction_id": transaction_id,
        "language": language,
        "text": ANNOUNCE[language].format(amount=spoken_amount(p["amount_paise"], language)),
        "text_en": f"Received {shown} rupees.",
        "question": None if q is None else {
            "question_id": q["question_id"],
            "text": question_text(p["payer_name"], p["amount_paise"], language),
            "text_en": question_text_en(p["payer_name"], p["amount_paise"]),
        },
        **extra,
    }


@router.post("/voice/interpret")
def interpret(body: InterpretIn, conn: sqlite3.Connection = Depends(get_conn)):
    """REAL (Asitha): reads the actual text. Rules first; Charulatha's LLM interpreter for what the rules can't read."""
    require_merchant_422(body.merchant_id)
    return interpreter.interpret(conn, merchant_id=body.merchant_id, language=body.language, text=body.text,
                                 open_question_id=body.open_question_id)


@router.post("/voice/answer")
def answer(body: AnswerIn, conn: sqlite3.Connection = Depends(get_conn)):
    """REAL (Asitha): fixed templates + positional slot check + TTS; facts from finance.summary."""
    if body.intent != "ASK_DAILY_PROFIT":
        raise errors.validation_error("Only ASK_DAILY_PROFIT has a spoken answer", field="intent")
    return daily_profit(conn, merchant_id=body.merchant_id, language=body.language, day=body.date)


@router.post("/voice/speak")
def speak(body: SpeakIn):
    """REAL: Sarvam Bulbul TTS through the client, cached by text (repeats are free and instant).
    Unreachable Sarvam or a cache miss in cache_only is 503: the frontend then uses the device voice or text."""
    require_merchant_422(body.merchant_id)
    if body.language not in ("ta", "te"):
        raise errors.validation_error("Speech is available in Tamil and Telugu", field="language")
    res = sarvam.tts(body.text, body.language)
    return {"audio_id": res.audio_id, "audio_url": f"/api/audio/{res.audio_id}", "from_cache": res.from_cache}


@router.get("/audio/{audio_id}")
def get_audio(audio_id: str):
    path = sarvam.find_audio(audio_id)
    if path is None:
        raise errors.not_found(f"Unknown audio {audio_id}", audio_id=audio_id)
    return FileResponse(path, media_type="audio/wav")
