"""The committed sample notice and its demo key (shared helper; Asitha). Used by notice/analyse.py, and by
the real analyse() when it lands.

demo_key "sample_notice_v1" may only be used with the committed image assets/notice/sample_notice.png, checked by
sha256 like the recorded demo clips (cache/sarvam_demo/demo_clips.json, written by
`python -m backend.app.sarvam.register_demo_clips`):
- the registered hash is the truth when present;
- the image exists but is not registered: its own hash is used, with a warning to register it;
- no image committed yet: any file is accepted, with a warning (the fallback for the demo until the image lands).
"""
from __future__ import annotations

import hashlib
import logging

from .. import errors
from ..config import REPO_ROOT
from ..sarvam import client as sarvam

SAMPLE_DEMO_KEY = "sample_notice_v1"
SAMPLE_FILE = REPO_ROOT / "assets" / "notice" / "sample_notice.png"
log = logging.getLogger("naanayam")


def _shown(path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def expected_sha256() -> str | None:
    registered = sarvam.load_demo_clips().get(SAMPLE_DEMO_KEY)
    if registered:
        return registered
    if SAMPLE_FILE.exists():
        log.warning("%s exists but is not registered; run python -m backend.app.sarvam.register_demo_clips",
                    _shown(SAMPLE_FILE))
        return hashlib.sha256(SAMPLE_FILE.read_bytes()).hexdigest()
    return None


def check_sample_file(file_bytes: bytes) -> bool:
    """True when the bytes are the committed sample; False when no sample is committed yet (accepted, warned).
    Raises 422 when a sample is known and the bytes differ."""
    expected = expected_sha256()
    if expected is None:
        log.warning("No sample notice committed yet (%s): demo_key %s accepts any file", _shown(SAMPLE_FILE),
                    SAMPLE_DEMO_KEY)
        return False
    if hashlib.sha256(file_bytes).hexdigest() != expected:
        raise errors.validation_error("file does not match the sample notice", field="file", demo_key=SAMPLE_DEMO_KEY)
    return True
