"""
Scrape a batch of reference genes from TIMER3 for use as a golden-standard
benchmark dataset. Stores one JSON file per gene under data/scraped/.

Run with:
    uv run python -m reproduce.scrape_golden
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from timer3 import Timer3Client

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "scraped"

# 20 genes covering tumor suppressors, oncogenes, immune markers, housekeeping
GOLDEN_GENES = [
    # Tumor suppressors
    "TP53", "RB1", "PTEN", "BRCA1", "APC",
    # Oncogenes
    "EGFR", "KRAS", "MYC", "BRAF", "PIK3CA",
    # Immune markers
    "CD8A", "FOXP3", "IFNG", "GZMB", "PDCD1", "CD274", "CTLA4",
    # Housekeeping
    "ACTB", "GAPDH",
    # Random sanity check
    "AAAS",
]


async def main(genes: list[str] = GOLDEN_GENES, purity_adj: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "purity" if purity_adj else "no_purity"
    async with Timer3Client(headless=True) as client:
        for i, gene in enumerate(genes, 1):
            out = OUT_DIR / f"{gene}_{suffix}.json"
            if out.exists():
                print(f"[{i}/{len(genes)}] {gene}: cached, skipping")
                continue
            try:
                r = await client.immune_gene(gene=gene, purity_adj=purity_adj)
                out.write_text(json.dumps(r.table))
                print(f"[{i}/{len(genes)}] {gene}: {len(r.table)} rows -> {out.name}")
            except Exception as e:
                print(f"[{i}/{len(genes)}] {gene}: FAILED {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
