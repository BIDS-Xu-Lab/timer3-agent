"""
Compute Spearman(gene_expression, immune_infiltration) per cancer label,
mirroring TIMER3's Immune_Gene heatmap.

Usage:
    from reproduce.compute import compute_gene
    df = compute_gene("EGFR")   # long-form: cancer, feature, n, rho
"""
from __future__ import annotations

import gzip
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .cancer_map import build_sample_labels

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EXPR_GZ = DATA_DIR / "expression_pancan.tsv.gz"
INFL_CSV = Path("/Users/hh667/Downloads/infiltration_estimation_for_tcga.csv")


@lru_cache(maxsize=1)
def _load_expr_header() -> list[str]:
    """Sample IDs from the expression matrix header row."""
    with gzip.open(EXPR_GZ, "rt") as f:
        header = f.readline().rstrip("\n").split("\t")
    return header[1:]  # drop the leading 'sample' label


@lru_cache(maxsize=1)
def _load_infiltration() -> pd.DataFrame:
    df = pd.read_csv(INFL_CSV)
    df = df.rename(columns={"cell_type": "sample"}).set_index("sample")
    return df


@lru_cache(maxsize=1)
def _load_labels() -> pd.DataFrame:
    return build_sample_labels()


def _stream_gene_row(gene: str) -> np.ndarray:
    """Linearly scan the gz file for a gene row. ~1-2s per query."""
    target = gene + "\t"
    with gzip.open(EXPR_GZ, "rt") as f:
        f.readline()  # header
        for line in f:
            if line.startswith(target):
                parts = line.rstrip("\n").split("\t")
                return np.array(parts[1:], dtype=float)
    raise KeyError(f"Gene not found in expression matrix: {gene!r}")


def compute_gene(gene: str) -> pd.DataFrame:
    """
    Returns long-form DataFrame with columns:
        cancer, feature, n, rho

    where rho is the Spearman correlation between the gene's expression
    and one immune feature, restricted to samples in that cancer label.
    """
    expr_samples = _load_expr_header()
    expr_vec = pd.Series(_stream_gene_row(gene), index=expr_samples, name=gene)
    expr_vec = expr_vec[~expr_vec.index.duplicated(keep="first")]

    infl = _load_infiltration()
    infl = infl[~infl.index.duplicated(keep="first")]
    labels = _load_labels().drop_duplicates(subset=["sample", "label"])

    # Align: only samples present in BOTH expression and infiltration
    common = expr_vec.index.intersection(infl.index)
    expr_vec = expr_vec.loc[common]
    infl = infl.loc[common]
    labels = labels[labels["sample"].isin(common)]

    features = list(infl.columns)
    out = []
    for cancer, sub in labels.groupby("label"):
        samples = sub["sample"].values
        x = expr_vec.loc[samples].values
        sub_infl = infl.loc[samples]
        n = len(samples)
        # vectorised: scipy.spearmanr handles columns at once
        # but it returns a full matrix; we want correlation of x vs each col.
        # Doing per-column rankdata-then-pearson is faster:
        from scipy.stats import rankdata

        x_rank = rankdata(x)
        x_rank_centered = x_rank - x_rank.mean()
        x_norm = np.sqrt((x_rank_centered ** 2).sum())

        for feat in features:
            y = sub_infl[feat].values
            if np.all(np.isnan(y)) or np.nanstd(y) == 0:
                rho = np.nan
            else:
                # Handle NaNs: pairwise complete obs
                mask = ~np.isnan(y)
                if mask.sum() < 3:
                    rho = np.nan
                else:
                    yr = rankdata(y[mask])
                    xr = rankdata(x[mask])
                    xr_c = xr - xr.mean()
                    yr_c = yr - yr.mean()
                    denom = np.sqrt((xr_c ** 2).sum() * (yr_c ** 2).sum())
                    rho = (xr_c * yr_c).sum() / denom if denom > 0 else np.nan
            out.append((cancer, feat, n, rho))

    return pd.DataFrame(out, columns=["cancer", "feature", "n", "rho"])


if __name__ == "__main__":
    import sys
    gene = sys.argv[1] if len(sys.argv) > 1 else "EGFR"
    df = compute_gene(gene)
    print(df.head(20))
    print(f"\nTotal rows: {len(df)} ({df['cancer'].nunique()} cancers x {df['feature'].nunique()} features)")
    out_path = DATA_DIR.parent / f"local_{gene}.parquet"
    df.to_parquet(out_path)
    print(f"Wrote {out_path}")
