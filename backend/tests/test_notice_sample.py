"""demo_key sample_notice_v1 is bound to the committed sample image by sha256 (like the demo clips)."""
import hashlib
import json
import logging

import pytest

from app.config import get_settings
from app.notice import sample

pytestmark = pytest.mark.timeout(900)


def _post(c, data):
    return c.post("/api/notices/analyse", data={"merchant_id": "M001", "demo_key": "sample_notice_v1"},
                  files={"file": ("sample_notice.png", data, "image/png")})


def _register(digest):
    path = get_settings().cache_root / "sarvam_demo" / "demo_clips.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    clips = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    clips["sample_notice_v1"] = digest
    path.write_text(json.dumps(clips), encoding="utf-8")


def test_no_sample_committed_yet_keeps_current_behaviour_and_warns(real, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(sample, "SAMPLE_FILE", tmp_path / "missing" / "sample_notice.png")
    with caplog.at_level(logging.WARNING, logger="naanayam"):
        r = _post(real, b"anything at all")
    assert r.status_code == 201 and r.json()["from_cache"] is True
    assert any("No sample notice committed yet" in m for m in caplog.messages)


def test_registered_sample_accepts_only_that_file(real, monkeypatch, tmp_path):
    image = tmp_path / "sample_notice.png"
    image.write_bytes(b"\x89PNG committed sample")
    monkeypatch.setattr(sample, "SAMPLE_FILE", image)
    _register(hashlib.sha256(image.read_bytes()).hexdigest())
    ok = _post(real, image.read_bytes())
    assert ok.status_code == 201
    assert real.get(f"/api/merchants/M001/notices/{ok.json()['notice_id']}/evidence").status_code == 200
    wrong = _post(real, b"\x89PNG some other image")
    assert wrong.status_code == 422 and wrong.json()["error"]["details"]["field"] == "file"
    assert wrong.json()["error"]["message"] == "file does not match the sample notice"


def test_committed_but_unregistered_sample_is_still_enforced(real, monkeypatch, tmp_path, caplog):
    image = tmp_path / "sample_notice.png"
    image.write_bytes(b"\x89PNG committed but not registered")
    monkeypatch.setattr(sample, "SAMPLE_FILE", image)
    with caplog.at_level(logging.WARNING, logger="naanayam"):
        assert _post(real, b"other bytes").status_code == 422
        assert _post(real, image.read_bytes()).status_code == 201
    assert any("not registered" in m for m in caplog.messages)


def test_register_script_includes_the_sample(monkeypatch, tmp_path):
    from app.sarvam import register_demo_clips

    image = tmp_path / "sample_notice.png"
    image.write_bytes(b"\x89PNG")
    monkeypatch.setattr(register_demo_clips, "SAMPLE_FILE", image)
    assert register_demo_clips.build()["sample_notice_v1"] == hashlib.sha256(b"\x89PNG").hexdigest()
    monkeypatch.setattr(register_demo_clips, "SAMPLE_FILE", tmp_path / "none.png")
    assert "sample_notice_v1" not in register_demo_clips.build()
