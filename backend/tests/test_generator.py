"""Synthetic data generator (DATA_AND_LOGIC section 4) and demo-day scripts (section 3)."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from data.generator import demo_scripts, params
from data.generator.generate import FIXED_UNANSWERED, M001_DEMO_CUSTOMERS, generate
from data.generator.run import label_mix

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def gen():
    return generate(42)


@pytest.fixture(scope="session")
def pay(gen):
    df = gen.payments.merge(gen.labels, on="transaction_id")
    df["dt"] = df.timestamp.map(datetime.fromisoformat)
    return df


def test_deterministic_for_seed():
    a, b = generate(42, only=["M001", "M101"]), generate(42, only=["M001", "M101"])
    pd.testing.assert_frame_equal(a.payments, b.payments)
    pd.testing.assert_frame_equal(a.expenses, b.expenses)
    c = generate(7, only=["M101"])
    assert not c.payments.equals(a.payments[a.payments.merchant_id == "M101"].reset_index(drop=True))


def test_merchants(gen):
    m = gen.merchants.set_index("merchant_id")
    assert list(m.index[:3]) == ["M001", "M002", "M003"]
    assert m.loc[["M001", "M002", "M003"], "business_category"].tolist() == ["VEGETABLES", "FRUITS", "MIXED_KIRANA"]
    evals = m.loc[params.EVAL_MERCHANTS]
    assert evals.business_category.value_counts().to_dict() == params.EVAL_CATEGORY_COUNTS
    assert evals.loc[params.TEST_MERCHANTS].business_category.nunique() == 5  # test set has every category
    assert len(params.TRAIN_MERCHANTS) == 70 and len(params.TEST_MERCHANTS) == 30
    assert not set(params.TRAIN_MERCHANTS) & set(params.TEST_MERCHANTS)
    assert evals.volume_scale.between(*params.SCALE_RANGE).all()


def test_period_and_ids(pay):
    assert pay.dt.min() >= datetime.fromisoformat("2026-08-01T00:00:00+05:30")
    assert pay.dt.max() < datetime.fromisoformat("2026-11-15T00:00:00+05:30")  # nothing on DEMO_DATE
    assert pay.transaction_id.is_unique
    assert pay.transaction_id.str.fullmatch(r"TXN-M\d{3}-\d{8}-\d{3}").all()
    assert (pay.transaction_id.str[9:17] == pay.dt.map(lambda d: d.strftime("%Y%m%d"))).all()
    assert pay.timestamp.str.endswith("+05:30").all()
    assert (pay.amount_paise > 0).all() and pay.amount_paise.dtype.kind == "i"


def test_shop_hours_and_category_clip(gen, pay):
    shop = pay[pay.payer_role.isin(["regular_customer", "walk_in"])]
    secs = shop.dt.map(lambda d: d.hour * 3600 + d.minute * 60 + d.second)
    assert secs.between(5 * 3600 + 1800, 21 * 3600 + 1800).all()
    cats = gen.merchants.set_index("merchant_id").business_category
    for cat, cfg in params.CATEGORY.items():
        part = shop[shop.merchant_id.map(cats) == cat]
        assert part.amount_paise.between(cfg["lo"] * 100, cfg["hi"] * 100).all(), cat


def test_fixed_unanswered_payments(pay):
    fixed = pay[pay.payer_role == "fixed_unanswered"].sort_values("dt")
    assert len(fixed) == 3
    expected = [(pid, f"{day.isoformat()}T20:05:00+05:30", rupees * 100) for pid, day, rupees in FIXED_UNANSWERED]
    assert list(zip(fixed.payer_id, fixed.timestamp, fixed.amount_paise)) == expected
    assert fixed.payer_name.tolist() == ["Mani", "Jaya", "Prabhu"]
    assert (fixed.merchant_id == "M001").all() and (fixed.payment_type == "P2P").all()
    assert (fixed.payer_vpa_kind == "PERSONAL").all() and (fixed.true_label == "FAMILY").all()
    # payers with no other history anywhere
    assert pay[pay.payer_id.isin(fixed.payer_id)].shape[0] == 3


def test_fixed_unanswered_never_refunded_or_reversed(gen, pay):
    fixed = set(pay[pay.payer_role == "fixed_unanswered"].transaction_id)
    assert not fixed & set(gen.refunds.transaction_id) and not fixed & set(gen.reversals.transaction_id)


def test_no_history_for_demo_day_first_payers(pay):
    assert pay[pay.payer_id.isin(["P90001", "P90011"])].empty  # Lakshmi R, Srinivas


def test_karthik(gen, pay):
    k = pay[pay.payer_id == "P90002"].sort_values("dt")
    assert (k.merchant_id == "M001").all() and len(k) >= 12
    assert (k.payment_type == "P2P").all() and (k.true_label == "FAMILY").all()
    assert k.amount_paise.isin([100000, 150000, 200000, 300000]).all()
    assert k.dt.diff().dropna().max() <= timedelta(days=9, hours=23)
    cfg = gen.family_config
    assert cfg.to_dict("records") == [{
        "merchant_id": "M001", "payer_id": "P90002", "relation_label": "Thambi (brother)",
        "added_at": "2026-08-01T05:00:00+05:30", "added_via": "SETUP",
    }]


def test_selvi_mixed_payer(pay):
    s = pay[pay.payer_id == "P90003"]
    sales, fam = s[s.true_label == "SALE"], s[s.true_label == "FAMILY"]
    assert len(sales) == 2 and len(fam) == 3
    assert (sales.payment_type == "P2M").all() and (sales.amount_paise % 500 != 0).all()
    assert (fam.payment_type == "P2P").all() and (fam.amount_paise % 50000 == 0).all()


def test_anbu_mess(pay):
    a = pay[pay.payer_id == "P20001"].sort_values("dt")
    assert (a.merchant_id == "M001").all() and (a.payer_vpa_kind == "BUSINESS").all()
    assert (a.payment_type == "P2M").all() and a.amount_paise.between(60000, 150000).all()
    days = a.dt.map(lambda d: d.date()).diff().dropna().map(lambda x: x.days)
    assert days.between(1, 3).all()
    assert a.dt.min().date().isoformat() <= "2026-08-03"


def test_hotel_sri_sai_is_m002_business_buyer(pay):
    h = pay[pay.payer_id == "P20011"]
    assert len(h) > 20 and (h.merchant_id == "M002").all() and (h.payer_vpa_kind == "BUSINESS").all()


def test_m001_demo_customers_are_established_regulars(pay):
    m001 = pay[pay.merchant_id == "M001"]
    counts = m001.payer_id.value_counts()
    for pid, name in M001_DEMO_CUSTOMERS:
        rows = m001[m001.payer_id == pid]
        assert counts.get(pid, 0) >= 5, (pid, counts.get(pid, 0))
        assert (rows.payer_name == name).all() and (rows.payer_vpa_kind == "PERSONAL").all()
        assert (rows.payer_role == "regular_customer").all()
    # customer IDs are in the P10001-P19999 range for demo merchants
    demo = pay[pay.merchant_id.isin(["M001", "M002", "M003"]) & pay.payer_role.isin(["regular_customer", "walk_in"])]
    assert demo.payer_id.str.fullmatch(r"P1\d{4}").all()


def test_refunds_and_reversals(gen, pay):
    rf, rv = gen.refunds, gen.reversals
    assert len(rf) > 0 and len(rv) > 0
    assert rf.refund_id.is_unique and rv.transaction_id.is_unique
    assert not set(rf.transaction_id) & set(rv.transaction_id)  # refunded or reversed, never both
    p = pay.set_index("transaction_id")
    joined = rf.merge(p[["amount_paise", "true_label", "dt"]], left_on="transaction_id", right_index=True,
                      suffixes=("", "_payment"))
    assert (joined.amount_paise <= joined.amount_paise_payment).all() and (joined.amount_paise > 0).all()
    assert (joined.true_label == "SALE").all()
    rf_dt = rf.timestamp.map(datetime.fromisoformat)
    assert (rf_dt > joined.dt).all() and (rf_dt - joined.dt <= timedelta(days=2)).all()
    rv_dt = rv.timestamp.map(datetime.fromisoformat)
    rv_pay = p.loc[rv.transaction_id, "dt"].to_numpy()
    assert all(a > b and a - b <= timedelta(days=1) for a, b in zip(rv_dt, rv_pay))
    end = datetime.fromisoformat("2026-11-14T21:30:00+05:30")
    assert (rf_dt <= end).all() and (rv_dt <= end).all()


def test_expenses(gen):
    e = gen.expenses
    assert set(e.merchant_id) == {"M001", "M002", "M003"}
    assert e.client_request_id.is_unique
    assert e.category.isin(["STOCK_PURCHASE", "TRANSPORT", "PACKAGING", "RENT"]).all()
    rent = e[e.category == "RENT"]
    assert (rent.amount_paise == 600000).all() and rent.timestamp.str[8:10].eq("05").all()
    m001_stock = e[(e.merchant_id == "M001") & (e.category == "STOCK_PURCHASE")]
    assert len(m001_stock) == len(set(m001_stock.timestamp.str[:10])) == 106  # daily
    assert m001_stock.amount_paise.between(250000, 450000).all()
    voice = e[e.input_source == "VOICE"]
    assert voice.language.notna().all() and e[e.input_source == "MANUAL"].language.isna().all()


def test_label_mix_has_both_classes(pay):
    for merchants in (params.TRAIN_MERCHANTS, params.TEST_MERCHANTS):
        part = pay[pay.merchant_id.isin(merchants)]
        assert (part.true_label == "FAMILY").sum() > 100 and (part.true_label == "SALE").sum() > 1000


def test_label_mix_count_and_value_share(gen, pay):
    mix = label_mix(gen)
    splits = {"overall", "demo", "train_calibration", "test_merchants_all_dates", "test_set"}
    assert set(mix["count_share"]) == set(mix["value_share"]) == set(mix["family_payments"]) == splits
    fam = pay[pay.true_label == "FAMILY"]
    assert mix["family_payments"]["overall"] == len(fam)
    assert mix["count_share"]["overall"] == round(len(fam) / len(pay), 6)
    assert mix["value_share"]["overall"] == round(fam.amount_paise.sum() / pay.amount_paise.sum(), 6)
    assert 0.002 < mix["count_share"]["overall"] < 0.01  # about 0.5% by count (DATA 4.3)
    assert mix["value_share"]["overall"] > mix["count_share"]["overall"]  # family transfers are large
    in_period = pay.timestamp.str[:10].between("2026-10-16", "2026-11-14")
    test_fam = pay[pay.merchant_id.isin(params.TEST_MERCHANTS) & in_period & (pay.true_label == "FAMILY")]
    assert mix["family_payments"]["test_set"] == len(test_fam)


# --- demo-day scripts ---------------------------------------------------------
def test_m001_script(gen):
    s = demo_scripts.build(gen, "M001")
    items = s["payments"]
    assert len(items) == 15
    assert [i["request"]["transaction_id"] for i in items] == [f"TXN-M001-20261115-{n:03d}" for n in range(1, 16)]
    sales = sum(i["request"]["amount_paise"] for i in items if i["expected_final_classification"] == "SALE")
    assert sales == 482000  # DATA 3.3: 4,820
    last = items[-1]
    assert last["request"]["payer_id"] == "P90001" and last["request"]["payer_name"] == "Lakshmi R"
    assert last["expected_action"] == "ASK_MERCHANT" and last["request"]["payment_type"] == "P2P"
    assert [i["expected_action"] for i in items[:14]] == ["AUTO_CLASSIFY"] * 14
    assert s["expense"]["amount_paise"] == 310000 and s["expense"]["timestamp"] == "2026-11-15T05:40:00+05:30"
    assert s["answer"] == {"demo_index": 15, "confirmed_category": "FAMILY", "channel": "VOICE",
                           "remember_payer": True, "utterance_text": s["answer"]["utterance_text"]}
    names = json.loads((REPO / "contract/fixtures/demo_script_M001.json").read_text(encoding="utf-8"))
    assert [i["request"]["payer_name"] for i in items] == [i["payer_name"] for i in names["items"]]


def test_m002_script(gen, pay):
    s = demo_scripts.build(gen, "M002")
    reqs = [i["request"] for i in s["payments"]]
    assert len(reqs) == 11
    total = sum(r["amount_paise"] for r in reqs)
    sales = sum(r["amount_paise"] for r, i in zip(reqs, s["payments"]) if i["expected_final_classification"] == "SALE")
    assert (total, sales, total - sales) == (785000, 635000, 150000)  # DATA 3.4
    assert s["expense"]["amount_paise"] == 420000
    counts = pay[pay.merchant_id == "M002"].payer_id.value_counts()
    for r in reqs:
        if r["payer_id"] not in ("P20011", "P90011"):
            assert counts.get(r["payer_id"], 0) >= 5 and r["payer_vpa_kind"] == "PERSONAL"


def test_committed_scripts_match_generator(gen):
    for mid in ("M001", "M002"):
        path = REPO / "data" / "demo" / f"{mid}_demo_day.json"
        assert path.exists(), f"run python -m data.generator.run --seed 42 ({path} missing)"
        assert json.loads(path.read_text(encoding="utf-8")) == demo_scripts.build(gen, mid)


def test_backend_never_reads_ground_truth():
    app = REPO / "backend" / "app"
    hits = [p for p in app.rglob("*.py") if re.search(r"labels\.parquet|true_label|payer_role", p.read_text(encoding="utf-8"))]
    assert hits == []
