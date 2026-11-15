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
        "DEMO_TIME": "",  # tests control the time of day with wall_clock; a developer's .env must not pin it
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


def build_test_seed(path):
    """A small seed.db: demo merchants, Karthik configured as family, and two history payments
    (Karthik auto-FAMILY, and one older unanswered question on 2026-10-29)."""
    from app import clock, db, repo
    from app.schemas import PaymentIn
    from app.services.payments import create_payment
    from data.generator.generate import DEMO_MERCHANTS, FAMILY_CONFIG, NAMED_PAYERS

    db.init_db(path)
    conn = db.connect(path)
    try:
        with db.write_tx(conn):
            for m in DEMO_MERCHANTS:
                repo.insert_merchant(conn, {**m, "city": "Chennai", "created_at": "2026-08-01T05:00:00+05:30"})
            for f in FAMILY_CONFIG:
                repo.ensure_payer(conn, f["payer_id"], *NAMED_PAYERS[f["payer_id"]])
                repo.add_family_payer(conn, f["merchant_id"], f["payer_id"], f["relation_label"], f["added_at"], f["added_via"])
        history = [
            ("TXN-M001-20261020-050", "P90002", "Karthik", 200000, "2026-10-20T19:10:00+05:30"),
            ("TXN-M001-20261029-042", "P90004", "Mani", 300000, "2026-10-29T20:05:00+05:30"),
        ]
        for txn, pid, name, amount, ts in history:
            with clock.frozen_at(clock.parse(ts)):  # history is written at its own time, like seed_demo
                create_payment(conn, PaymentIn(transaction_id=txn, merchant_id="M001", payer_id=pid, payer_name=name,
                                               payer_vpa_kind="PERSONAL", amount_paise=amount, payment_type="P2P",
                                               timestamp=ts))
    finally:
        conn.close()


@pytest.fixture
def fake_q(monkeypatch):
    """Deterministic stand-in for the trained model in persistence tests (the real model is tested on the
    real seed in test_demo_day.py): P2P + personal + multiple of Rs 500 -> q 0.6, else 0.0001."""
    from app.classifier import model
    from app.classifier.features import FEATURES

    idx = {n: i for i, n in enumerate(FEATURES)}

    def q(vec):
        looks_family = vec[idx["is_p2p"]] and not vec[idx["is_business_vpa"]] and vec[idx["is_round_500"]]
        return 0.6 if looks_family else 0.0001  # sales clear any threshold in the grid (<= 0.999)

    monkeypatch.setattr(model, "q_model", q)


@pytest.fixture
def seeded(make_client, tmp_path, wall_clock, fake_q):
    """Client on a database restored from a small test seed via POST /demo/reset. Wall clock 21:00.
    Uses the fake_q stand-in model so these tests check persistence, not model quality."""
    wall_clock("21:00:00")
    seed = tmp_path / "seed.db"
    with make_client(DEMO_SEED_DB=str(seed)) as c:
        build_test_seed(seed)
        r = c.post("/api/demo/reset", json={})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
def wall_clock(monkeypatch):
    """Set the real IST wall-clock time used by app.clock: wall_clock("12:00:00")."""
    from datetime import datetime, time

    def _set(hhmmss: str):
        t = time.fromisoformat(hhmmss)
        monkeypatch.setattr(clock, "_wall_now", lambda: datetime.combine(datetime(2030, 1, 1).date(), t, tzinfo=clock.IST))

    return _set


@pytest.fixture
def real(make_client, wall_clock):
    """Client on the committed demo seed (data/demo/seed.db) after /demo/reset. Wall clock 21:00."""
    from app.config import DEMO_DATA_DIR

    seed = DEMO_DATA_DIR / "seed.db"
    if not seed.exists():
        pytest.skip("run the release gate first")
    wall_clock("21:00:00")
    with make_client(DEMO_SEED_DB=str(seed)) as c:
        assert c.post("/api/demo/reset", json={}).status_code == 200
        yield c


def run_m001_demo(c, *, answer=True):
    """Expense + the 15 scripted payments (+ Lakshmi answered FAMILY with remember). Returns the ASK payment."""
    import json

    from app.config import DEMO_DATA_DIR

    script = json.loads((DEMO_DATA_DIR / "M001_demo_day.json").read_text(encoding="utf-8"))
    assert c.post("/api/expenses", json=script["expense"]).status_code == 201
    pays = [c.post("/api/demo/next-payment", json={"merchant_id": "M001"}).json() for _ in range(15)]
    if answer:
        r = c.post(f"/api/payments/{pays[14]['transaction_id']}/confirm", json={
            "merchant_id": "M001", "question_id": pays[14]["question_id"], "confirmed_category": "FAMILY",
            "channel": "VOICE", "utterance_text": None, "remember_payer": True})
        assert r.status_code == 201
    return pays[14]
