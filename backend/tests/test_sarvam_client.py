"""Sarvam client: content-hash cache, DEMO_MODE behaviour, demo clip verification (test list item 16)."""
import base64
import hashlib
import json

import httpx
import pytest

from app.errors import ApiError
from app.sarvam import client


class FakeSarvam:
    """Replaces client._send. Returns a transcript derived from the uploaded bytes."""

    def __init__(self, fail_with=None):
        self.calls = 0
        self.fail_with = fail_with

    def __call__(self, method, url, *, timeout, headers=None, files=None, data=None, json=None):
        self.calls += 1
        request = httpx.Request(method, url)
        if self.fail_with == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if self.fail_with == "500":
            return httpx.Response(500, json={}, request=request)
        if url.endswith("/speech-to-text"):
            audio = files["file"][1]
            return httpx.Response(200, json={"transcript": f"heard-{hashlib.sha256(audio).hexdigest()[:8]}"}, request=request)
        if url.endswith("/text-to-speech"):
            return httpx.Response(200, json={"audios": [base64.b64encode(b"RIFFfakewav").decode()]}, request=request)
        if url.endswith("/chat/completions"):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"intent":"UNKNOWN"}'}}]}, request=request)
        return httpx.Response(404, request=request)


@pytest.fixture
def fake(monkeypatch):
    f = FakeSarvam()
    monkeypatch.setattr(client, "_send", f)
    return f


def test_cache_key_depends_on_input_and_params():
    base = client.cache_key("stt", "m1", {"language_code": "ta-IN"}, b"aaa")
    assert base != client.cache_key("stt", "m1", {"language_code": "ta-IN"}, b"aab")
    assert base != client.cache_key("stt", "m2", {"language_code": "ta-IN"}, b"aaa")
    assert base != client.cache_key("stt", "m1", {"language_code": "te-IN"}, b"aaa")
    assert base != client.cache_key("tts", "m1", {"language_code": "ta-IN"}, b"aaa")


def test_cache_only_miss_raises_cache_miss(env, fake):
    env(DEMO_MODE="cache_only", SARVAM_API_KEY="k")
    with pytest.raises(ApiError) as exc:
        client.stt(b"live bytes", "ta")
    assert (exc.value.status, exc.value.code) == (503, "CACHE_MISS")
    assert fake.calls == 0


def test_cache_first_calls_once_then_cached_live(env, fake):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k")
    first = client.stt(b"judge speaking", "ta")
    second = client.stt(b"judge speaking", "ta")
    assert (first.recognition_mode, first.from_cache) == ("LIVE", False)
    assert (second.recognition_mode, second.from_cache) == ("CACHED_LIVE", True)
    assert first.text == second.text and fake.calls == 1


def test_live_mode_always_calls(env, fake):
    env(DEMO_MODE="live", SARVAM_API_KEY="k")
    client.stt(b"x", "ta")
    client.stt(b"x", "ta")
    assert fake.calls == 2


def test_live_upload_never_returns_demo_transcript(env, fake, tmp_path):
    """A live recording that differs from a demo clip gets its own transcript, never the clip's."""
    clip = b"recorded demo clip bytes"
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k", SARVAM_CACHE_DIR="demo")
    _register_clip("ta/expense_koyambedu", clip)
    demo = client.stt(clip, "ta", demo_key="ta/expense_koyambedu")
    live = client.stt(b"a different live recording", "ta")
    assert demo.recognition_mode == "RECORDED_DEMO"
    assert live.recognition_mode == "LIVE"
    assert live.text != demo.text


def test_demo_key_with_wrong_bytes_is_422(env, fake):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k")
    _register_clip("ta/expense_koyambedu", b"the real clip")
    with pytest.raises(ApiError) as exc:
        client.stt(b"not the clip", "ta", demo_key="ta/expense_koyambedu")
    assert (exc.value.status, exc.value.code) == (422, "VALIDATION_ERROR")
    assert fake.calls == 0


def test_unknown_demo_key_is_422(env, fake):
    with pytest.raises(ApiError) as exc:
        client.stt(b"x", "ta", demo_key="ta/nope")
    assert exc.value.status == 422


def test_recorded_demo_works_offline_once_cached(env, fake):
    clip = b"clip"
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k", SARVAM_CACHE_DIR="demo")
    _register_clip("ta/confirm_yes", clip)
    warm = client.stt(clip, "ta", demo_key="ta/confirm_yes")
    env(DEMO_MODE="cache_only", SARVAM_API_KEY="", SARVAM_CACHE_DIR="dev")
    stage = client.stt(clip, "ta", demo_key="ta/confirm_yes")
    assert stage.text == warm.text and stage.from_cache and stage.recognition_mode == "RECORDED_DEMO"


def test_retry_then_unavailable_on_timeout(env, monkeypatch):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k")
    f = FakeSarvam(fail_with="timeout")
    monkeypatch.setattr(client, "_send", f)
    with pytest.raises(ApiError) as exc:
        client.stt(b"x", "ta")
    assert exc.value.code == "SARVAM_UNAVAILABLE" and f.calls == 2


def test_retry_on_5xx(env, monkeypatch):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k")
    f = FakeSarvam(fail_with="500")
    monkeypatch.setattr(client, "_send", f)
    with pytest.raises(ApiError):
        client.chat([{"role": "user", "content": "hi"}])
    assert f.calls == 2


def test_missing_key_is_unavailable(env, fake):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="")
    with pytest.raises(ApiError) as exc:
        client.stt(b"x", "ta")
    assert exc.value.code == "SARVAM_UNAVAILABLE" and fake.calls == 0


def test_tts_stores_audio_and_serves_by_audio_id(env, fake):
    env(DEMO_MODE="cache_first", SARVAM_API_KEY="k")
    result = client.tts("₹3,100 செலவு சேமிச்சுட்டேன்.", "ta")
    assert result.audio_id.startswith("AUD-") and len(result.audio_id) == 20
    assert client.find_audio(result.audio_id).read_bytes() == b"RIFFfakewav"
    again = client.tts("₹3,100 செலவு சேமிச்சுட்டேன்.", "ta")
    assert again.from_cache and again.audio_id == result.audio_id and fake.calls == 1


def test_calls_are_logged(env, fake):
    settings = env(DEMO_MODE="cache_first", SARVAM_API_KEY="k", SARVAM_PERSON="tester")
    client.stt(b"x", "ta")
    lines = (settings.logs_dir / "sarvam_calls.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    assert entry["service"] == "stt" and entry["ok"] is True and entry["person"] == "tester"


def _register_clip(key: str, data: bytes) -> None:
    from app.config import get_settings

    path = get_settings().cache_root / client.DEMO_DIR / client.DEMO_CLIPS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    clips = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    clips[key] = hashlib.sha256(data).hexdigest()
    path.write_text(json.dumps(clips), encoding="utf-8")
