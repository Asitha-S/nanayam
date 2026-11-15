"""python -m data.generator.run --seed 42

Writes data/generated/*.parquet (+ labels.parquet ground truth) and the demo-day scripts in
data/demo/, then prints the realised label mix and per-role counts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import demo_scripts
from .generate import Generated, generate

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLITS = {
    "demo (M001-M003)": lambda m: m in ("M001", "M002", "M003"),
    "train+calibration (M101-M130)": lambda m: m.startswith("M1") and 101 <= int(m[1:]) <= 130,
    "test (M131-M140)": lambda m: m.startswith("M1") and 131 <= int(m[1:]) <= 140,
}


def write(gen: Generated, out_dir: Path, demo_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("merchants", "payers", "payments", "refunds", "reversals", "expenses", "labels", "family_config"):
        getattr(gen, name).to_parquet(out_dir / f"{name}.parquet", index=False)
    demo_dir.mkdir(parents=True, exist_ok=True)
    for mid in ("M001", "M002"):
        if mid in set(gen.merchants.merchant_id):
            script = demo_scripts.build(gen, mid)
            (demo_dir / f"{mid}_demo_day.json").write_text(
                json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )


def summary(gen: Generated) -> str:
    df = gen.payments.merge(gen.labels, on="transaction_id")
    lines = [f"payments {len(df):,}  payers {len(gen.payers):,}  refunds {len(gen.refunds):,}  "
             f"reversals {len(gen.reversals):,}  expenses {len(gen.expenses):,}"]
    lines.append("\nLabel mix by count (target about 93% SALE / 7% FAMILY):")
    for split, pred in SPLITS.items():
        part = df[df.merchant_id.map(pred)]
        if len(part):
            fam = (part.true_label == "FAMILY").mean()
            lines.append(f"  {split:32s} n={len(part):>8,}  SALE {1 - fam:6.2%}  FAMILY {fam:6.2%}")
    fam = (df.true_label == "FAMILY").mean()
    lines.append(f"  {'all':32s} n={len(df):>8,}  SALE {1 - fam:6.2%}  FAMILY {fam:6.2%}")
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
    write(gen, args.out, args.demo_out)
    print(f"Generated with seed {args.seed} -> {args.out}")
    print(summary(gen))


if __name__ == "__main__":
    main()
