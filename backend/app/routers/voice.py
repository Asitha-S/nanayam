"""Voice endpoints (contract section 6). Routers are Asitha's; the logic behind them is
Charulatha's backend/app/voice/ module.

REAL: /voice/answer (Asitha). STUB (fixtures) until Charulatha's modules land: transcribe, interpret, speak.
The demo-clip hash check is already real: a demo_key with the wrong bytes is a 422.
"""
import sqlite3

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from .. import errors
from ..deps import get_conn
from ..sarvam import client as sarvam
from ..voice.answer import daily_profit
from ..schemas import AnswerIn, InterpretIn, SpeakIn, VoiceLanguage
from ..stubs import fixture, require_merchant_422

router = APIRouter(tags=["voice"])

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~30 s of 16 kHz WAV is ~1 MB; anything this big is too long
PROFIT_WORDS = ("லாபம்", "மீதம்", "labham", "laabam", "meedham", "లాభం", "profit")


@router.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: VoiceLanguage = Form(...),
    merchant_id: str = Form(...),
    demo_key: str | None = Form(None),
):
    require_merchant_422(merchant_id)
    data = await audio.read()
    if not data:
        raise errors.validation_error("Empty audio", field="audio")
    if len(data) > MAX_AUDIO_BYTES:
        raise errors.validation_error("Audio too long (max 30 s)", field="audio")
    if demo_key:
        sarvam.verify_demo_clip(demo_key, data)
        return fixture("voice_transcribe_recorded")
    return fixture("voice_transcribe_live")


@router.post("/voice/interpret")
def interpret(body: InterpretIn):
    require_merchant_422(body.merchant_id)
    text = body.text.lower()
    if body.open_question_id:
        return fixture("voice_interpret_confirm")
    if any(w in text for w in PROFIT_WORDS):
        return fixture("voice_interpret_profit")
    return fixture("voice_interpret_expense")


@router.post("/voice/answer")
def answer(body: AnswerIn, conn: sqlite3.Connection = Depends(get_conn)):
    """REAL (Asitha): fixed templates + positional slot check + TTS; facts from finance.summary."""
    if body.intent != "ASK_DAILY_PROFIT":
        raise errors.validation_error("Only ASK_DAILY_PROFIT has a spoken answer", field="intent")
    return daily_profit(conn, merchant_id=body.merchant_id, language=body.language, day=body.date)


@router.post("/voice/speak")
def speak(body: SpeakIn):
    require_merchant_422(body.merchant_id)
    return fixture("voice_speak")


@router.get("/audio/{audio_id}")
def get_audio(audio_id: str):
    path = sarvam.find_audio(audio_id)
    if path is None:
        raise errors.not_found(f"Unknown audio {audio_id}", audio_id=audio_id)
    return FileResponse(path, media_type="audio/wav")
