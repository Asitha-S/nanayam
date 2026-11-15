"""python -m data.generator.run --seed 42

Writes data/generated/*.parquet (+ labels.parquet ground truth, label_mix.json) and the demo-day
scripts in data/demo/, then prints the realised label mix and per-role counts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import demo_scripts, params
from .generate import Generated, generate

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = {"M001", "M002", "M003"}
TRAIN = set(params.TRAIN_MERCHANTS)
TEST = set(params.TEST_MERCHANTS)
SPLITS = {  # name -> row filter on a payments+labels frame
    "overall": lambda df: df,
    "demo": lambda df: df[df.merchant_id.isin(DEMO)],
    "train_calibration": lambda df: df[df.merchant_id.isin(TRAIN)],
    "test_merchants_all_dates": lambda df: df[df.merchant_id.isin(TEST)],
    "test_set": lambda df: df[df.merchant_id.isin(TEST) & df.timestamp.str[:10].between(
        params.TEST_PERIOD[0].isoformat(), params.TEST_PERIOD[1].isoformat())],
}


def label_mix(gen: Generated) -> dict:
    """FAMILY share by count and by value (sum of FAMILY amounts / sum of all amounts), per split."""
    df = gen.payments.merge(gen.labels, on="transaction_id")
    out: dict = {"count_share": {}, "value_share": {}, "family_payments": {}, "payments": {}}
    for name, pick in SPLITS.items():
        part = pick(df)
        fam = part[part.true_label == "FAMILY"]
        out["payments"][name] = int(len(part))
        out["family_payments"][name] = int(len(fam))
        out["count_share"][name] = round(len(fam) / len(part), 6) if len(part) else None
        total = int(part.amount_paise.sum())
        out["value_share"][name] = round(int(fam.amount_paise.sum()) / total, 6) if total else None
    out["definition"] = ("FAMILY share. count_share = FAMILY payments / all payments; value_share = sum of FAMILY "
                         "amounts / sum of all amounts. test_set = test merchants M171-M200 in the test period "
                         f"{params.TEST_PERIOD[0]} to {params.TEST_PERIOD[1]}.")
    return out


def write(gen: Generated, out_dir: Path, demo_dir: Path, seed: int) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("merchants", "payers", "payments", "refunds", "reversals", "expenses", "labels", "family_config"):
        getattr(gen, name).to_parquet(out_dir / f"{name}.parquet", index=False)
    mix = {"seed": seed, **label_mix(gen)}
    (out_dir / "label_mix.json").write_text(json.dumps(mix, indent=2) + "\n", encoding="utf-8")
    demo_dir.mkdir(parents=True, exist_ok=True)
    for mid in ("M001", "M002"):
        if mid in set(gen.merchants.merchant_id):
            script = demo_scripts.build(gen, mid)
            (demo_dir / f"{mid}_demo_day.json").write_text(
                json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return mix


def summary(gen: Generated, mix: dict) -> str:
    df = gen.payments.merge(gen.labels, on="transaction_id")
    lines = [f"payments {len(df):,}  payers {len(gen.payers):,}  refunds {len(gen.refunds):,}  "
             f"reversals {len(gen.reversals):,}  expenses {len(gen.expenses):,}"]
    lines.append("\nFAMILY share (target about 0.5% of payments by count):")
    lines.append(f"  {'split':26s} {'payments':>9s} {'FAMILY':>7s} {'by count':>9s} {'by value':>9s}")
    for name in SPLITS:
        lines.append(f"  {name:26s} {mix['payments'][name]:>9,} {mix['family_payments'][name]:>7,} "
                     f"{mix['count_share'][name]:>9.2%} {mix['value_share'][name]:>9.2%}")
    n_test = mix["family_payments"]["test_set"]
    verdict = "OK" if n_test >= params.TARGET_TEST_FAMILY_PAYMENTS else "BELOW TARGET"
    lines.append(f"\nFAMILY payments in the test set: {n_test} (target >= {params.TARGET_TEST_FAMILY_PAYMENTS}: {verdict})")
    lines.append("\nPer-role counts (payments, distinct payers, label):")
    roles = df.groupby("payer_role").agg(payments=("transaction_id", "size"), payers=("payer_id", "nunique"),
                                         label=("true_label", lambda s: "/".join(sorted(s.unique()))))
    for role, r in roles.sort_values("payments", ascending=False).iterrows():
        lines.append(f"  {role:18s} {r.payments:>8,}  {r.payers:>7,}  {r.label}")
    lines.append("\nM001: " + ", ".join(
        f"{role} {n}" for role, n in df[df.merchant_id == "M001"].payer_role.value_counts().items()))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "generated")
    ap.add_argument("--demo-out", type=Path, default=REPO_ROOT / "data" / "demo")
    args = ap.parse_args()
    gen = generate(args.seed)
    mix = write(gen, args.out, args.demo_out, args.seed)
    print(f"Generated with seed {args.seed} -> {args.out}")
    print(summary(gen, mix))


if __name__ == "__main__":
    pd.set_option("display.width", 120)
    main()
