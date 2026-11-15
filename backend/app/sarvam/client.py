"""Sarvam client with content-hash cache (VOICE_AND_NOTICE section 3). Nobody calls Sarvam directly.

Cache key = sha256(service + model_id + canonical JSON of params + sha256(input)). There is no key
that ignores the input, so a live recording can never return a scripted transcript.

DEMO_MODE:
  cache_only  - cached response or CACHE_MISS (503). Never calls Sarvam.
  cache_first - cached response; on miss call Sarvam, store, return.
  live        - always call Sarvam and store the result.

Reads check cache/sarvam_demo/ first, then cache/sarvam_dev/. New responses are written to the
folder chosen by SARVAM_CACHE_DIR (dev or demo).

Recorded demo clips: cache/sarvam_demo/demo_clips.json maps demo_key -> sha256 of the committed
WAV. stt(..., demo_key=...) first checks the uploaded bytes match (else 422), then uses the same
content-hash cache, and reports recognition_mode RECORDED_DEMO.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass

from pathlib import Path
from typing import Any, Callable

import httpx

from .. import clock, errors
from ..config import get_settings
from . import models

DEMO_DIR = "sarvam_demo"
DEV_DIR = "sarvam_dev"
DEMO_CLIPS_FILE = "demo_clips.json"


# --- results ------------------------------------------------------------------
@dataclass(frozen=True)
class SttResult:
    text: str
    language: str
    recognition_mode: str  # LIVE | CACHED_LIVE | RECORDED_DEMO
    from_cache: bool
    audio_sha256: str
    raw: dict


@dataclass(frozen=True)
class ChatResult:
    content: str
    from_cache: bool
    raw: dict


@dataclass(frozen=True)
class TtsResult:
    audio_id: str
    audio_bytes: bytes
    mime: str
    from_cache: bool


@dataclass(frozen=True)
class VisionResult:
    text: str
    from_cache: bool
    raw: dict


# --- hashing and cache --------------------------------------------------------
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(service: str, model_id: str, params: dict, input_bytes: bytes) -> str:
    material = "\n".join([service, model_id, canonical_json(params), sha256_hex(input_bytes)])
    return sha256_hex(material.encode("utf-8"))


def audio_id_for(lang: str, voice_id: str, text: str) -> str:
    """AUD-{first 16 hex of sha256(lang + voice_id + text)} (DATA_AND_LOGIC section 2)."""
    return "AUD-" + sha256_hex(f"{lang}{voice_id}{text}".encode("utf-8"))[:16]


def _cache_dirs() -> tuple[Path, Path]:
    root = get_settings().cache_root
    return root / DEMO_DIR, root / DEV_DIR


def _write_dir() -> Path:
    demo, dev = _cache_dirs()
    return demo if get_settings().sarvam_cache_dir == "demo" else dev


def _read_cache(key: str) -> tuple[dict, Path] | None:
    for folder in _cache_dirs():
        path = folder / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), folder
    return None


def _write_cache(key: str, record: dict, blob: bytes | None = None) -> None:
    folder = _write_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if blob is not None:
        (folder / f"{key}.wav").write_bytes(blob)
    (folder / f"{key}.json").write_text(canonical_json(record), encoding="utf-8")


def _cached_call(
    service: str,
    model_id: str,
    params: dict,
    input_bytes: bytes,
    call: Callable[[], tuple[dict, bytes | None]],
) -> tuple[dict, bytes | None, bool]:
    """Returns (response json, optional binary blob, from_cache)."""
    mode = get_settings().demo_mode
    key = cache_key(service, model_id, params, input_bytes)
    if mode != "live":
        hit = _read_cache(key)
        if hit is not None:
            record, folder = hit
            blob_path = folder / f"{key}.wav"
            blob = blob_path.read_bytes() if blob_path.exists() else None
            return record["response"], blob, True
        if mode == "cache_only":
            raise errors.cache_miss(
                f"No cached Sarvam response for this {service} input and DEMO_MODE=cache_only",
                service=service,
            )
    response, blob = call()
    _write_cache(
        key,
        {
            "service": service,
            "model_id": model_id,
            "params": params,
            "input_sha256": sha256_hex(input_bytes),
            "created_at": clock.iso(clock.real_now()),
            "response": response,
        },
        blob,
    )
    return response, blob, False


# --- demo clips ---------------------------------------------------------------
def load_demo_clips() -> dict[str, str]:
    path = _cache_dirs()[0] / DEMO_CLIPS_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def verify_demo_clip(demo_key: str, audio_bytes: bytes) -> None:
    expected = load_demo_clips().get(demo_key)
    if expected is None:
        raise errors.validation_error(f"Unknown demo_key {demo_key!r}", field="demo_key")
    if sha256_hex(audio_bytes) != expected:
        raise errors.validation_error("audio does not match demo clip", field="audio", demo_key=demo_key)


# --- HTTP ---------------------------------------------------------------------
def _send(method: str, url: str, *, timeout: float, **kwargs) -> httpx.Response:
    """The single network call. Tests replace this."""
    with httpx.Client(timeout=timeout) as http:
        return http.request(method, url, **kwargs)


def _log_call(service: str, model_id: str, latency_ms: int, ok: bool, status: int | None) -> None:
    settings = get_settings()
    try:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        line = {
            "time": clock.iso(clock.real_now()),
            "service": service,
            "model_id": model_id,
            "latency_ms": latency_ms,
            "ok": ok,
            "status": status,
            "person": settings.sarvam_person,
        }
        with (settings.logs_dir / "sarvam_calls.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break a call


def _post(service: str, model_id: str, path: str, timeout: float, **kwargs) -> httpx.Response:
    """POST with one retry on timeout or 5xx, then SARVAM_UNAVAILABLE."""
    key = get_settings().sarvam_api_key
    if not key:
        raise errors.sarvam_unavailable("SARVAM_API_KEY is not set", service=service)
    headers = {models.AUTH_HEADER: key}
    url = models.BASE_URL + path
    last_problem = "unknown"
    for _attempt in range(2):
        start = time.monotonic()
        try:
            resp = _send("POST", url, timeout=timeout, headers=headers, **kwargs)
        except httpx.TimeoutException:
            _log_call(service, model_id, int((time.monotonic() - start) * 1000), False, None)
            last_problem = "timeout"
            continue
        except httpx.HTTPError as exc:
            _log_call(service, model_id, int((time.monotonic() - start) * 1000), False, None)
            raise errors.sarvam_unavailable(f"Could not reach Sarvam: {exc.__class__.__name__}", service=service)
        latency = int((time.monotonic() - start) * 1000)
        _log_call(service, model_id, latency, resp.is_success, resp.status_code)
        if resp.is_success:
            return resp
        if resp.status_code >= 500:
            last_problem = f"HTTP {resp.status_code}"
            continue
        raise errors.sarvam_unavailable(
            f"Sarvam rejected the request (HTTP {resp.status_code})", service=service, status=resp.status_code
        )
    raise errors.sarvam_unavailable(f"Sarvam unavailable ({last_problem})", service=service)


# --- public API ---------------------------------------------------------------
def stt(audio_bytes: bytes, lang: str, demo_key: str | None = None, filename: str = "audio.wav") -> SttResult:
    if not audio_bytes:
        raise errors.validation_error("Empty audio", field="audio")
    if demo_key is not None:
        verify_demo_clip(demo_key, audio_bytes)
    params = {"model": models.STT_MODEL, "language_code": models.LANGUAGE_CODES[lang]}

    def call():
        resp = _post(
            "stt",
            models.STT_MODEL,
            models.STT_PATH,
            models.TIMEOUT_STT,
            files={"file": (filename, audio_bytes)},
            data=params,
        )
        return resp.json(), None

    response, _, from_cache = _cached_call("stt", models.STT_MODEL, params, audio_bytes, call)
    if demo_key is not None:
        mode = "RECORDED_DEMO"
    else:
        mode = "CACHED_LIVE" if from_cache else "LIVE"
    return SttResult(
        text=response.get("transcript", ""),
        language=lang,
        recognition_mode=mode,
        from_cache=from_cache,
        audio_sha256=sha256_hex(audio_bytes),
        raw=response,
    )


def chat(messages: list[dict], schema: dict | None = None) -> ChatResult:
    params: dict = {"model": models.CHAT_MODEL, "temperature": 0}
    if schema is not None:
        params["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "intent_output",
                "schema": schema,
            },
        }
    input_bytes = canonical_json(messages).encode("utf-8")

    def call():
        body = {"model": models.CHAT_MODEL, "messages": messages, "temperature": 0}
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "intent_output",
                    "schema": schema,
                },
            }
        resp = _post("chat", models.CHAT_MODEL, models.CHAT_PATH, models.TIMEOUT_CHAT, json=body)
        return resp.json(), None

    response, _, from_cache = _cached_call("chat", models.CHAT_MODEL, params, input_bytes, call)
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = ""
    return ChatResult(content=content, from_cache=from_cache, raw=response)


def tts(text: str, lang: str) -> TtsResult:
    speaker = models.TTS_SPEAKERS[lang]
    params = {"model": models.TTS_MODEL, "speaker": speaker, "target_language_code": models.LANGUAGE_CODES[lang]}

    def call():
        body = {"text": text, **params}
        resp = _post("tts", models.TTS_MODEL, models.TTS_PATH, models.TIMEOUT_TTS, json=body)
        payload = resp.json()
        audios = payload.get("audios") or []
        if not audios:
            raise errors.sarvam_unavailable("Sarvam TTS returned no audio", service="tts")
        blob = base64.b64decode(audios[0])
        meta = {k: v for k, v in payload.items() if k != "audios"}
        return meta, blob

    _, blob, from_cache = _cached_call("tts", models.TTS_MODEL, params, text.encode("utf-8"), call)
    if blob is None:
        raise errors.sarvam_unavailable("Cached TTS entry has no audio file", service="tts")
    audio_id = audio_id_for(lang, speaker, text)
    save_audio(audio_id, blob)
    return TtsResult(audio_id=audio_id, audio_bytes=blob, mime="audio/wav", from_cache=from_cache)


def vision(file_bytes: bytes, demo_key: str | None = None, filename: str = "notice.png") -> VisionResult:
    """demo_key is only a label for the committed sample; the cache is still keyed on file bytes."""
    params = {"model": models.VISION_MODEL}

    def call():
        if models.VISION_PATH is None:
            raise errors.sarvam_unavailable("Sarvam vision endpoint not configured yet", service="vision")
        resp = _post(
            "vision",
            models.VISION_MODEL,
            models.VISION_PATH,
            models.TIMEOUT_VISION,
            files={"file": (filename, file_bytes)},
            data=params,
        )
        return resp.json(), None

    response, _, from_cache = _cached_call("vision", models.VISION_MODEL, params, file_bytes, call)
    return VisionResult(text=response.get("text", ""), from_cache=from_cache, raw=response)


# --- audio store (served by GET /audio/{audio_id}) -----------------------------
def _audio_dirs() -> tuple[Path, Path]:
    demo, dev = _cache_dirs()
    return demo / "audio", dev / "audio"


def save_audio(audio_id: str, blob: bytes) -> None:
    folder = _write_dir() / "audio"
    path = folder / f"{audio_id}.wav"
    if any((d / f"{audio_id}.wav").exists() for d in _audio_dirs()):
        return
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def find_audio(audio_id: str) -> Path | None:
    if not audio_id.startswith("AUD-") or not all(c in "0123456789abcdef" for c in audio_id[4:]):
        return None
    for folder in _audio_dirs():
        path = folder / f"{audio_id}.wav"
        if path.exists():
            return path
    return None
