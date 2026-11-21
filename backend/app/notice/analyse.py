"""POST /notices/analyse (contract section 9). Owner: Asitha (this fallback). The real reader was planned for
Charulatha and is not written yet.

FALLBACK STUB (agreed 2026-11-14) until a real analyse() lands; it replaces this function's body,
keeping the signature, and the router needs no change:
- demo_key "sample_notice_v1" with the committed sample image (sha256 checked by notice/sample.py; 422 for any
  other file once the image is committed): the sample notice's known fields (period and amount from
  data/demo/notice_numbers.json, the other fields from contract/fixtures/notice_analyse.json) are saved with
  notice.store.save_notice and returned, marked from_cache true (as the cached reading of the sample would be);
- any other input: 503 SARVAM_UNAVAILABLE (reading arbitrary notices is not available yet).
The Tamil explanation (planned for Charulatha) is not written yet; until then explanation.text is null.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .. import errors, repo
from ..config import DEMO_DATA_DIR
from ..stubs import fixture
from .sample import SAMPLE_DEMO_KEY, check_sample_file
from .store import save_notice


def _sample_fields() -> dict:
    numbers = json.loads((DEMO_DATA_DIR / "notice_numbers.json").read_text(encoding="utf-8"))
    fields = fixture("notice_analyse")["fields"]
    fields["period_start"]["value"] = numbers["period_start"]
    fields["period_end"]["value"] = numbers["period_end"]
    fields["amount_questioned_paise"]["value"] = numbers["amount_questioned_paise"]
    return fields


def analyse(conn: sqlite3.Connection, *, merchant_id: str, file_bytes: bytes, demo_key: str | None) -> dict:
    merchant = repo.require_merchant_in_body(conn, merchant_id)
    if demo_key != SAMPLE_DEMO_KEY:
        raise errors.sarvam_unavailable("Reading notices is not available yet; only the committed sample "
                                        f"(demo_key {SAMPLE_DEMO_KEY!r}) can be analysed", service="vision")
    check_sample_file(file_bytes)
    fields = _sample_fields()
    notice_id = save_notice(conn, merchant_id=merchant_id, file_sha256=hashlib.sha256(file_bytes).hexdigest(),
                            fields=fields)
    template = fixture("notice_analyse")
    return {
        "notice_id": notice_id,
        "merchant_id": merchant_id,
        "fields": fields,
        "explanation": {"language": merchant["preferred_language"], "text": None, "audio_id": None},
        "missing_fields": [name for name, f in fields.items() if f.get("origin") == "NOT_FOUND"],
        "disclaimer": template["disclaimer"],
        "from_cache": True,
    }
