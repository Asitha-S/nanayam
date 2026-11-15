"""The smoke journey (scripts/smoke.py) in-process, at a real time of day before every scripted event."""
import pytest
from fastapi.testclient import TestClient

from app.config import DEMO_DATA_DIR
from scripts.smoke import DEMO_TIME, Smoke

SEED = DEMO_DATA_DIR / "seed.db"
pytestmark = [pytest.mark.skipif(not SEED.exists(), reason="run the release gate first"), pytest.mark.timeout(900)]


def _smoke(env, wall_clock, demo_time: str) -> Smoke:
    wall_clock("03:00:00")  # before the 05:40 expense and every scripted payment
    env(DEMO_SEED_DB=str(SEED), DEMO_TIME=demo_time)
    from app.main import create_app

    from app.config import get_settings

    with TestClient(create_app(), base_url="http://testserver/api") as http:
        smoke = Smoke(http, get_settings().db_path)
        smoke.run()
    return smoke


def test_smoke_passes_at_any_time_of_day_with_demo_time(env, wall_clock):
    smoke = _smoke(env, wall_clock, DEMO_TIME)
    failed = [r for r in smoke.rows if not r[1]]
    assert DEMO_TIME == "21:30" and not failed, failed
    assert len(smoke.rows) == 21


def test_without_demo_time_the_morning_expense_is_in_the_future(env, wall_clock):
    smoke = _smoke(env, wall_clock, "")
    expense = next(r for r in smoke.rows if r[0].startswith("expense"))
    assert expense[1] is False and "422" in expense[2]
