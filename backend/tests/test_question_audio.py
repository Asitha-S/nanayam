"""GET /merchants/{id}/questions: question_audio_id comes from TTS when speech is available, else null (contract 4)."""
from types import SimpleNamespace

from app import errors
from app.services import payments


def test_question_card_gets_audio_when_speech_is_available(real, monkeypatch):
    calls = []

    def fake_tts(text, lang):
        calls.append((text, lang))
        return SimpleNamespace(audio_id=f"AUD-test-{len(calls)}", from_cache=True)

    monkeypatch.setattr(payments.sarvam, "tts", fake_tts)
    r = real.get("/api/merchants/M001/questions?status=OPEN")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "the seed keeps older open questions"
    assert [i["question_audio_id"] for i in items] == [f"AUD-test-{n}" for n in range(1, len(items) + 1)]
    assert calls == [(i["question_text"], "ta") for i in items]  # the card's own text, in the merchant's language


def test_question_card_falls_back_to_text_when_speech_fails(real, monkeypatch):
    def failing_tts(text, lang):
        raise errors.sarvam_unavailable("Sarvam down", service="tts")

    monkeypatch.setattr(payments.sarvam, "tts", failing_tts)
    r = real.get("/api/merchants/M001/questions?status=OPEN")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and all(i["question_audio_id"] is None and i["question_text"] for i in items)


def test_no_speech_in_cache_only_mode_without_a_cached_entry(real):
    # the test environment runs DEMO_MODE=cache_only with an empty cache: text only, never an error
    items = real.get("/api/merchants/M001/questions?status=OPEN").json()["items"]
    assert items and all(i["question_audio_id"] is None for i in items)
