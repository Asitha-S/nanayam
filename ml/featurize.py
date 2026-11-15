"""Features for every payment of the evaluation merchants (M101-M280), by incremental replay.

Each merchant's payments are walked in (timestamp, transaction_id) order; features are computed BEFORE
the payment is added to the history (DATA_AND_LOGIC 11.2: strictly earlier payments only, no labels).
Writes data/generated/features.parquet.
"""
from __future__ import annotations

import time

import pandas as pd

from .common import GENERATED  # noqa: F401  (also puts backend/ on sys.path)
from app.classifier.features import FEATURES, MerchantHistory, Pay  # noqa: E402
from app.clock import parse  # noqa: E402

OUT = GENERATED / "features.parquet"


def featurize(merchant_ids: list[str] | None = None) -> pd.DataFrame:
    return featurize_frames(pd.read_parquet(GENERATED / "merchants.parquet"),
                            pd.read_parquet(GENERATED / "payments.parquet"),
                            pd.read_parquet(GENERATED / "labels.parquet"), merchant_ids)


def featurize_frames(merchants: pd.DataFrame, payments: pd.DataFrame, labels: pd.DataFrame,
                     merchant_ids: list[str] | None = None) -> pd.DataFrame:
    merchants = merchants.set_index("merchant_id")
    labels = labels.set_index("transaction_id")
    eval_ids = [m for m in merchants.index if m.startswith("M") and int(m[1:]) >= 101]
    wanted = set(merchant_ids or eval_ids)
    payments = payments[payments.merchant_id.isin(wanted)].sort_values(["merchant_id", "timestamp", "transaction_id"])

    rows = []
    for mid, group in payments.groupby("merchant_id", sort=True):
        history = MerchantHistory(merchants.loc[mid, "business_category"])
        for r in group.itertuples(index=False):
            pay = Pay(r.transaction_id, r.payer_id, int(r.amount_paise), r.payment_type, r.payer_vpa_kind,
                      parse(r.timestamp))
            f = history.features(pay)
            history.add(pay)
            rows.append((r.transaction_id, mid, r.payer_id, r.timestamp, int(r.amount_paise), *(f[n] for n in FEATURES)))
    df = pd.DataFrame(rows, columns=["transaction_id", "merchant_id", "payer_id", "timestamp", "amount_paise", *FEATURES])
    df["date"] = df.timestamp.str[:10]
    df = df.join(labels[["true_label", "payer_role"]], on="transaction_id")
    return df


def main() -> None:
    start = time.monotonic()
    df = featurize()
    df.to_parquet(OUT, index=False)
    print(f"Features for {len(df):,} payments of {df.merchant_id.nunique()} merchants -> {OUT} "
          f"({time.monotonic() - start:.0f} s)")


if __name__ == "__main__":
    main()
