"""The only source of "now" in the backend. Nothing else calls datetime.now().

Rules (agreed 2026-11-14):
- now() = DEMO_DATE + the real IST time of day.
- A ledger entry's created_at = max(now, event time, previous entry's created_at for that merchant),
  so created_at never goes backwards within a merchant's chain.
- The expense "not in the future" check uses the same effective now: max(now, previous created_at).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from .config import get_settings

# IST has no daylight saving, so a fixed offset is exact (and avoids needing tzdata on Windows).
IST = timezone(timedelta(hours=5, minutes=30), "IST")

# Set only by frozen_at(): replaying history (seed_demo, evaluation) writes entries at historical times.
_frozen: ContextVar[datetime | None] = ContextVar("naanayam_frozen_now", default=None)


def _wall_now() -> datetime:
    """Real current time in IST. Tests monkeypatch this."""
    return datetime.now(IST)


def real_now() -> datetime:
    """True wall-clock time in IST. Only for operational metadata (logs, cache records),
    never for business data, which uses now()."""
    return _wall_now().astimezone(IST).replace(microsecond=0)


def today() -> date:
    return get_settings().demo_date


def now() -> datetime:
    """DEMO_DATE combined with the real IST time of day (whole seconds), unless frozen_at() is active."""
    frozen = _frozen.get()
    if frozen is not None:
        return frozen
    wall = _wall_now().astimezone(IST)
    return datetime.combine(today(), wall.time().replace(microsecond=0), tzinfo=IST)


@contextmanager
def frozen_at(dt: datetime) -> Iterator[None]:
    """Make now() return dt inside the block. For replaying history only (seed_demo), never in request handling."""
    token = _frozen.set(to_ist(dt).replace(microsecond=0))
    try:
        yield
    finally:
        _frozen.reset(token)


def effective_now(prev_created_at: datetime | None = None) -> datetime:
    """now(), but never earlier than the merchant's latest ledger created_at."""
    candidates = [now()]
    if prev_created_at is not None:
        candidates.append(to_ist(prev_created_at))
    return max(candidates)


def created_at_for(event_time: datetime | None, prev_created_at: datetime | None) -> datetime:
    """created_at for a new ledger entry: max(now, event time, previous created_at)."""
    candidates = [effective_now(prev_created_at)]
    if event_time is not None:
        candidates.append(to_ist(event_time))
    return max(candidates)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime: timestamps must carry an offset")
    return dt.astimezone(IST)


def parse(value: str) -> datetime:
    """Parse an ISO 8601 timestamp that has an offset, returned in IST."""
    return to_ist(datetime.fromisoformat(value))


def iso(dt: datetime) -> str:
    """'2026-11-15T19:42:10+05:30'"""
    return to_ist(dt).isoformat(timespec="seconds")


def ist_date(dt: datetime) -> date:
    return to_ist(dt).date()
