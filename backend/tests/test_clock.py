import pytest
from datetime import date
from pathlib import Path

from app import clock


def test_now_is_demo_date_plus_wall_time(env, wall_clock):
    wall_clock("12:00:05")
    assert clock.iso(clock.now()) == "2026-11-15T12:00:05+05:30"
    assert clock.today() == date(2026, 11, 15)


def test_created_at_never_before_event_time(env, wall_clock):
    # Mentor round at 12:00 injects payment 15 (19:42): created_at must not precede the payment.
    wall_clock("12:00:00")
    event = clock.parse("2026-11-15T19:42:10+05:30")
    assert clock.iso(clock.created_at_for(event, None)) == "2026-11-15T19:42:10+05:30"


def test_created_at_never_goes_backwards(env, wall_clock):
    wall_clock("12:00:00")
    prev = clock.parse("2026-11-15T19:42:10+05:30")
    event = clock.parse("2026-11-15T06:12:10+05:30")
    assert clock.iso(clock.created_at_for(event, prev)) == "2026-11-15T19:42:10+05:30"


def test_created_at_is_now_when_later(env, wall_clock):
    wall_clock("20:00:00")
    prev = clock.parse("2026-11-15T19:42:10+05:30")
    event = clock.parse("2026-11-15T19:42:10+05:30")
    assert clock.iso(clock.created_at_for(event, prev)) == "2026-11-15T20:00:00+05:30"


def test_effective_now_uses_previous_created_at(env, wall_clock):
    wall_clock("12:00:00")
    prev = clock.parse("2026-11-15T19:43:02+05:30")
    assert clock.iso(clock.effective_now(prev)) == "2026-11-15T19:43:02+05:30"


def test_parse_converts_to_ist():
    assert clock.iso(clock.parse("2026-11-15T14:12:10+00:00")) == "2026-11-15T19:42:10+05:30"


def test_only_clock_calls_datetime_now():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name != "clock.py"
        and any(s in p.read_text(encoding="utf-8") for s in ("datetime.now(", "datetime.utcnow(", "date.today(", "time.time("))
    ]
    assert offenders == []


def test_frozen_at_overrides_now_only_inside_block(env, wall_clock):
    wall_clock("12:00:00")
    past = clock.parse("2026-10-29T20:05:00+05:30")
    with clock.frozen_at(past):
        assert clock.iso(clock.now()) == "2026-10-29T20:05:00+05:30"
        assert clock.iso(clock.created_at_for(past, None)) == "2026-10-29T20:05:00+05:30"
    assert clock.iso(clock.now()) == "2026-11-15T12:00:00+05:30"


def test_demo_time_pins_time_of_day(env, wall_clock, monkeypatch):
    wall_clock("03:12:45")
    monkeypatch.setenv("DEMO_TIME", "21:30")
    assert clock.iso(clock.now()) == "2026-11-15T21:30:00+05:30"
    assert clock.real_now().hour == 3  # logs and cache records keep the real time
    with clock.frozen_at(clock.parse("2026-10-29T20:05:00+05:30")):  # history replay still wins
        assert clock.iso(clock.now()) == "2026-10-29T20:05:00+05:30"
    monkeypatch.setenv("DEMO_TIME", "")
    assert clock.iso(clock.now()) == "2026-11-15T03:12:45+05:30"


@pytest.mark.parametrize("bad", ["9pm", "25:00", "21:61", "21"])
def test_demo_time_rejects_bad_values(env, monkeypatch, bad):
    monkeypatch.setenv("DEMO_TIME", bad)
    with pytest.raises(ValueError):
        clock.now()
