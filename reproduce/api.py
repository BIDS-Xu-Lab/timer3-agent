"""
Local API for querying precomputed Spearman correlations.

Usage:
    from reproduce.api import LocalTimer3
    api = LocalTimer3()  # loads ~300 MB once
    df = api.gene("EGFR")                     # all cancers x features
    df = api.gene("EGFR", cancer="BRCA-LumA")
    df = api.gene("EGFR", feature_substr="Macrophage")
"""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "lookup.npz"


class LocalTimer3:
    def __init__(self, path: Path = DATA):
        z = np.load(path, allow_pickle=False)
        self._rho = z["rho"]                    # (n_genes, n_cancers, n_features)
        self._n = z["n"]                        # (n_cancers,)
        self.genes = list(z["genes"].astype(str))
        self.cancers = list(z["cancers"].astype(str))
        self.features = list(z["features"].astype(str))

    @cached_property
    def _gene_idx(self) -> dict[str, int]:
        return {g: i for i, g in enumerate(self.genes)}

    @cached_property
    def _cancer_idx(self) -> dict[str, int]:
        return {c: i for i, c in enumerate(self.cancers)}

    def gene(
        self,
        gene: str,
        cancer: str | None = None,
        feature_substr: str | None = None,
    ) -> pd.DataFrame:
        """Long-form DataFrame: (cancer, feature, n, rho)."""
        if gene not in self._gene_idx:
            raise KeyError(f"Gene not in index: {gene!r}")
        gi = self._gene_idx[gene]

        if cancer is not None:
            if cancer not in self._cancer_idx:
                raise KeyError(f"Cancer not in index: {cancer!r}")
            ci = self._cancer_idx[cancer]
            mat = self._rho[gi, ci:ci + 1, :]
            cancers = [cancer]
            ns = self._n[ci:ci + 1]
        else:
            mat = self._rho[gi]
            cancers = self.cancers
            ns = self._n

        df = pd.DataFrame(mat, index=cancers, columns=self.features)
        df = df.stack().reset_index()
        df.columns = ["cancer", "feature", "rho"]
        n_map = dict(zip(cancers, ns))
        df["n"] = df["cancer"].map(n_map)
        df = df[["cancer", "feature", "n", "rho"]]

        if feature_substr is not None:
            df = df[df["feature"].str.contains(feature_substr, case=False, regex=False)]

        return df.reset_index(drop=True)


if __name__ == "__main__":
    import sys
    api = LocalTimer3()
    print(f"Loaded: {len(api.genes)} genes, {len(api.cancers)} cancers, {len(api.features)} features")
    g = sys.argv[1] if len(sys.argv) > 1 else "EGFR"
    df = api.gene(g)
    print(f"\n{g}: {len(df)} rows")
    print(df.head(10))
    print("\nMacrophage features:")
    print(api.gene(g, feature_substr="Macrophage").head(20))
