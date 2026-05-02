"""
Precompute Spearman(gene, immune feature) per cancer label for all genes.

Output: data/lookup.npz containing
    rho:      float32 array (n_genes, n_cancers, n_features)
    n:        int32   array (n_cancers,)            -- samples per cancer
    genes:    list[str]                              -- length n_genes
    cancers:  list[str]                              -- length n_cancers
    features: list[str]                              -- length n_features

Spearman = Pearson on ranks. NaN handling: per cancer, drop any sample
that has a NaN in ANY infiltration feature (only ~1.5% of rows have NaN).
"""
from __future__ import annotations

import gzip
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from .cancer_map import build_sample_labels

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW = DATA_DIR / "raw"
EXPR_GZ = RAW / "expression_pancan.tsv.gz"
INFL_CSV = Path("/Users/hh667/Downloads/infiltration_estimation_for_tcga.csv")
OUT_NPZ = DATA_DIR / "lookup.npz"


def load_expression_matrix() -> tuple[list[str], list[str], np.ndarray]:
    print(f"[expr] streaming {EXPR_GZ}")
    t0 = time.time()
    with gzip.open(EXPR_GZ, "rt") as f:
        header = f.readline().rstrip("\n").split("\t")
        samples = header[1:]
        genes: list[str] = []
        rows: list[np.ndarray] = []
        for i, line in enumerate(f):
            parts = line.rstrip("\n").split("\t")
            genes.append(parts[0])
            row = np.fromiter(
                (np.nan if v == "NA" else float(v) for v in parts[1:]),
                dtype=np.float32,
                count=len(parts) - 1,
            )
            rows.append(row)
            if (i + 1) % 5000 == 0:
                print(f"  {i + 1} genes loaded ({time.time() - t0:.1f}s)")
    mat = np.vstack(rows)
    seen, keep = set(), []
    for i, g in enumerate(genes):
        if g not in seen:
            seen.add(g)
            keep.append(i)
    mat = mat[keep]
    genes = [genes[i] for i in keep]

    # Impute NaN with row median (~1.7% of cells, concentrated in 20% of genes).
    # Filled values land near the gene's median rank — negligible effect on
    # Spearman vs other features, and avoids per-gene NaN bookkeeping.
    nan_mask = np.isnan(mat)
    if nan_mask.any():
        n_nan_genes = nan_mask.any(axis=1).sum()
        print(f"[expr] imputing NaN: {nan_mask.sum()} cells in {n_nan_genes} genes")
        for g in np.where(nan_mask.any(axis=1))[0]:
            row = mat[g]
            med = np.nanmedian(row)
            row[np.isnan(row)] = med if not np.isnan(med) else 0.0
    print(f"[expr] {mat.shape[0]} genes x {mat.shape[1]} samples ({time.time()-t0:.1f}s)")
    return samples, genes, mat


def rank_rows(mat: np.ndarray) -> np.ndarray:
    """Rank each row independently (scipy rankdata, average ties)."""
    out = np.empty_like(mat, dtype=np.float32)
    for i in range(mat.shape[0]):
        out[i] = rankdata(mat[i], method="average").astype(np.float32)
    return out


def main():
    expr_samples, genes, expr_mat = load_expression_matrix()
    expr_idx = {s: i for i, s in enumerate(expr_samples)}

    print("[infl] loading infiltration matrix")
    infl = pd.read_csv(INFL_CSV).rename(columns={"cell_type": "sample"})
    infl = infl.drop_duplicates(subset=["sample"]).set_index("sample")
    features = list(infl.columns)
    print(f"[infl] {infl.shape[0]} samples x {len(features)} features")

    print("[labels] building cancer-type labels")
    labels = build_sample_labels().drop_duplicates(["sample", "label"])
    cancers = sorted(labels["label"].unique())
    print(f"[labels] {labels['sample'].nunique()} samples, {len(cancers)} cancer labels")

    n_genes, n_cancers, n_features = len(genes), len(cancers), len(features)
    rho = np.full((n_genes, n_cancers, n_features), np.nan, dtype=np.float32)
    n_per_cancer = np.zeros(n_cancers, dtype=np.int32)

    for ci, cancer in enumerate(cancers):
        t0 = time.time()
        cancer_samples = labels.loc[labels["label"] == cancer, "sample"].tolist()
        common = [s for s in cancer_samples if s in expr_idx and s in infl.index]
        if not common:
            continue
        Y = infl.loc[common, features]
        # drop samples with any NaN
        keep_mask = ~Y.isna().any(axis=1).values
        if keep_mask.sum() < 5:
            continue
        common = [s for s, k in zip(common, keep_mask) if k]
        n = len(common)
        n_per_cancer[ci] = n

        col_idx = np.array([expr_idx[s] for s in common])
        X = expr_mat[:, col_idx]                     # (n_genes, n)
        Y = infl.loc[common, features].to_numpy(dtype=np.float32)  # (n, n_features)

        # Rank
        Xr = rank_rows(X)                            # (n_genes, n)
        Yr = rank_rows(Y.T).T                        # (n, n_features)

        # Center & normalize
        Xc = Xr - Xr.mean(axis=1, keepdims=True)
        Yc = Yr - Yr.mean(axis=0, keepdims=True)
        Xn = np.sqrt((Xc ** 2).sum(axis=1))          # (n_genes,)
        Yn = np.sqrt((Yc ** 2).sum(axis=0))          # (n_features,)
        denom = np.outer(Xn, Yn)
        num = Xc @ Yc                                # (n_genes, n_features)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = np.where(denom > 0, num / denom, np.nan)

        # Mask features with zero variance in this cancer
        zero_var = (Yc.std(axis=0) == 0)
        if zero_var.any():
            r[:, zero_var] = np.nan

        rho[:, ci, :] = r.astype(np.float32)
        print(f"  [{ci+1:2d}/{n_cancers}] {cancer:12s} n={n:4d}  {time.time()-t0:.1f}s")

    print(f"\n[save] writing {OUT_NPZ}")
    np.savez_compressed(
        OUT_NPZ,
        rho=rho,
        n=n_per_cancer,
        genes=np.array(genes),
        cancers=np.array(cancers),
        features=np.array(features),
    )
    size_mb = OUT_NPZ.stat().st_size / 1024 / 1024
    print(f"[save] done ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
