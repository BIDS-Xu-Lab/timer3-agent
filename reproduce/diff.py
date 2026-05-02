"""
Compare local Spearman computation against scraped TIMER3 numbers.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

# Map TIMER3 column header (e.g. "T cell CD8+\nTIMER") to CSV column
# (e.g. "T cell CD8+_TIMER"). Algorithms TIMER3 uses but the public CSV
# doesn't expose: ABIS, CONSENSUS_TME, ImmuCellAI, TIDE.
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


def scraped_to_long(scraped: list[dict]) -> pd.DataFrame:
    rows = []
    for row in scraped:
        m = re.match(r"^(.*?) \(n=(\d+)\)$", row["cancer"])
        if not m:
            continue
        cancer, n = m.group(1), int(m.group(2))
        for k, v in row.items():
            if k == "cancer":
                continue
            # k looks like "T cell CD8+\nTIMER"
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
            rows.append((cancer, feature, n, val))
    return pd.DataFrame(rows, columns=["cancer", "feature", "n_scraped", "rho_scraped"])


def main(gene: str = "EGFR"):
    scraped = json.load(open(ROOT / f"data/scraped/{gene}_no_purity.json"))
    s_long = scraped_to_long(scraped)
    local = pd.read_parquet(ROOT / f"data/local_{gene}.parquet")

    merged = local.merge(s_long, on=["cancer", "feature"], how="inner")
    merged["diff"] = merged["rho"] - merged["rho_scraped"]

    print(f"Compared {len(merged)} (cancer, feature) cells")
    print(f"  Mean |diff|:   {merged['diff'].abs().mean():.4f}")
    print(f"  Median |diff|: {merged['diff'].abs().median():.4f}")
    print(f"  Max |diff|:    {merged['diff'].abs().max():.4f}")
    print(f"  Pearson(local, scraped): "
          f"{merged[['rho','rho_scraped']].corr().iloc[0,1]:.4f}")

    # Show worst 10 mismatches
    print("\n--- Worst 10 disagreements ---")
    worst = merged.reindex(merged["diff"].abs().sort_values(ascending=False).index).head(10)
    print(worst[["cancer", "feature", "n", "n_scraped", "rho", "rho_scraped", "diff"]].to_string(index=False))

    print("\n--- Sample-size mismatches ---")
    n_mm = merged[merged["n"] != merged["n_scraped"]][["cancer", "n", "n_scraped"]].drop_duplicates()
    print(n_mm.to_string(index=False) if len(n_mm) else "  (none)")

    # Save merged
    out = ROOT / f"data/diff_{gene}.parquet"
    merged.to_parquet(out)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "EGFR")
