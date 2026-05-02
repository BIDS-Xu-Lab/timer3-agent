"""
Benchmark the local lookup against the scraped TIMER3 golden-standard.

Reads all data/scraped/<gene>_no_purity.json files, joins with the local
index, reports overall + stratified fidelity metrics.

Run:
    uv run python -m reproduce.benchmark
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .api import LocalTimer3

ROOT = Path(__file__).resolve().parent.parent
SCRAPED = ROOT / "data" / "scraped"

# TIMER3 algorithm token (in scraped column header) -> CSV column suffix
ALG_RENAME = {
    "MCP-COUNTER": "MCPCOUNTER",
    "EPIC": "EPIC",
    "TIMER": "TIMER",
    "CIBERSORT": "CIBERSORT",
    "CIBERSORT-ABS": "CIBERSORT-ABS",
    "QUANTISEQ": "QUANTISEQ",
    "XCELL": "XCELL",
}
COVERED_ALGS = set(ALG_RENAME)


def _scraped_to_long(scraped: list[dict], gene: str) -> pd.DataFrame:
    rows = []
    for row in scraped:
        m = re.match(r"^(.*?) \(n=(\d+)\)$", row["cancer"])
        if not m:
            continue
        cancer, n = m.group(1), int(m.group(2))
        for k, v in row.items():
            if k == "cancer":
                continue
            parts = k.split("\n")
            if len(parts) != 2:
                continue
            cell, alg = parts
            if alg not in COVERED_ALGS:
                continue
            feature = f"{cell}_{ALG_RENAME[alg]}"
            try:
                val = float(v)
            except (ValueError, TypeError):
                val = np.nan
            rows.append((gene, cancer, feature, n, val))
    return pd.DataFrame(rows, columns=["gene", "cancer", "feature", "n_scraped", "rho_scraped"])


def main():
    api = LocalTimer3()

    all_pairs = []
    for path in sorted(SCRAPED.glob("*_no_purity.json")):
        gene = path.stem.replace("_no_purity", "")
        scraped = json.loads(path.read_text())
        s = _scraped_to_long(scraped, gene)
        try:
            l = api.gene(gene)
        except KeyError:
            print(f"  [skip] {gene}: not in local index")
            continue
        l["gene"] = gene
        merged = l.merge(s, on=["gene", "cancer", "feature"], how="inner")
        all_pairs.append(merged)
        print(
            f"  [{gene:<8s}] {len(merged):>4d} cells, "
            f"Pearson(local, scraped) = "
            f"{merged[['rho','rho_scraped']].corr().iloc[0,1]:.3f}"
        )

    if not all_pairs:
        print("No scraped data to benchmark against.")
        return

    df = pd.concat(all_pairs, ignore_index=True)
    df = df.dropna(subset=["rho", "rho_scraped"])
    df["diff"] = df["rho"] - df["rho_scraped"]
    df["alg"] = df["feature"].str.rsplit("_", n=1).str[-1]

    print(f"\n=== Overall (n={len(df)} cells, {df['gene'].nunique()} genes) ===")
    print(f"  Pearson(local, scraped):     {df[['rho','rho_scraped']].corr().iloc[0,1]:.4f}")
    print(f"  Mean |diff|:                 {df['diff'].abs().mean():.4f}")
    print(f"  Median |diff|:               {df['diff'].abs().median():.4f}")
    print(f"  P95 |diff|:                  {df['diff'].abs().quantile(0.95):.4f}")
    print(f"  Cells within +-0.05:         {(df['diff'].abs() < 0.05).mean()*100:.1f}%")
    print(f"  Cells within +-0.10:         {(df['diff'].abs() < 0.10).mean()*100:.1f}%")

    # Restrict to cells where sample sizes match exactly
    exact = df[df["n"] == df["n_scraped"]].copy()
    print(f"\n=== Restricted to matching n ({len(exact)} cells / {len(df)}) ===")
    print(f"  Pearson(local, scraped):     {exact[['rho','rho_scraped']].corr().iloc[0,1]:.4f}")
    print(f"  Mean |diff|:                 {exact['diff'].abs().mean():.4f}")
    print(f"  Cells within +-0.05:         {(exact['diff'].abs() < 0.05).mean()*100:.1f}%")

    print("\n=== Per-algorithm (matching n) ===")
    g = exact.groupby("alg").apply(lambda d: pd.Series({
        "n_cells": len(d),
        "pearson": d[["rho", "rho_scraped"]].corr().iloc[0, 1],
        "mean_abs_diff": d["diff"].abs().mean(),
        "pct_within_0.05": (d["diff"].abs() < 0.05).mean(),
    }), include_groups=False).round(4)
    print(g.to_string())

    print("\n=== Per-gene (matching n) ===")
    g = exact.groupby("gene").apply(lambda d: pd.Series({
        "n_cells": len(d),
        "pearson": d[["rho", "rho_scraped"]].corr().iloc[0, 1] if len(d) > 2 else np.nan,
        "mean_abs_diff": d["diff"].abs().mean(),
    }), include_groups=False).round(4)
    print(g.to_string())

    print("\n=== Per-cancer (matching n) ===")
    g = exact.groupby("cancer").apply(lambda d: pd.Series({
        "n_cells": len(d),
        "pearson": d[["rho", "rho_scraped"]].corr().iloc[0, 1] if len(d) > 2 else np.nan,
        "mean_abs_diff": d["diff"].abs().mean(),
    }), include_groups=False).round(4)
    print(g.to_string())

    # Cancers where n drifts from TIMER3
    n_drift = (
        df[["cancer", "n", "n_scraped"]]
        .drop_duplicates()
        .assign(delta=lambda d: d["n"] - d["n_scraped"])
        .query("delta != 0")
        .sort_values("delta", key=abs, ascending=False)
    )
    if not n_drift.empty:
        print("\n=== Sample-size drift vs TIMER3 ===")
        print(n_drift.to_string(index=False))

    out = ROOT / "data" / "benchmark.parquet"
    df.to_parquet(out)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
