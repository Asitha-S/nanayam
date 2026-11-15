import pytest
from fastapi.testclient import TestClient

from app import clock
from app.config import get_settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated settings: temp DB, temp Sarvam cache and logs, no API key, demo tools on."""
    values = {
        "DEMO_MODE": "cache_only",
        "DEMO_DATE": "2026-11-15",
        "DB_PATH": str(tmp_path / "test.db"),
        "CONF_THRESHOLD": "0.90",
        "ENABLE_DEMO_TOOLS": "true",
        "SARVAM_CACHE_DIR": "dev",
        "SARVAM_CACHE_ROOT": str(tmp_path / "cache"),
        "LOGS_DIR": str(tmp_path / "logs"),
        "SARVAM_API_KEY": "",
    }

    def apply(**overrides):
        for k, v in {**values, **overrides}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return get_settings()

    apply()
    yield apply
    get_settings.cache_clear()


@pytest.fixture
def make_client(env):
    def _make(**overrides):
        env(**overrides)
        from app.main import create_app

        return TestClient(create_app())

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


@pytest.fixture
def wall_clock(monkeypatch):
    """Set the real IST wall-clock time used by app.clock: wall_clock("12:00:00")."""
    from datetime import datetime, time

    def _set(hhmmss: str):
        t = time.fromisoformat(hhmmss)
        monkeypatch.setattr(clock, "_wall_now", lambda: datetime.combine(datetime(2030, 1, 1).date(), t, tzinfo=clock.IST))

    return _set
