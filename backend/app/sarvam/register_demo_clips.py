"""Write cache/sarvam_demo/demo_clips.json from the committed demo WAV files.

Run from the repository root after recording or replacing a clip:
    python -m backend.app.sarvam.register_demo_clips

demo_key = path under assets/demo_audio/ without extension, e.g. "ta/expense_koyambedu"
(the language prefix is needed because ta/ and te/ share file names).
"""
from __future__ import annotations

import hashlib
import json

from ..config import REPO_ROOT, get_settings
from .client import DEMO_CLIPS_FILE, DEMO_DIR

AUDIO_ROOT = REPO_ROOT / "assets" / "demo_audio"


def build() -> dict[str, str]:
    clips = {}
    for wav in sorted(AUDIO_ROOT.rglob("*.wav")):
        key = wav.relative_to(AUDIO_ROOT).with_suffix("").as_posix()
        clips[key] = hashlib.sha256(wav.read_bytes()).hexdigest()
    return clips


def main() -> None:
    clips = build()
    out = get_settings().cache_root / DEMO_DIR / DEMO_CLIPS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clips, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(clips)} demo clips to {out}")
    for key, digest in clips.items():
        print(f"  {key}  {digest[:16]}...")


if __name__ == "__main__":
    main()
