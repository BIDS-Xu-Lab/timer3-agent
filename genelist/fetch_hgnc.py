"""
Download the HGNC reference gene list and emit a plain-text whitelist of
approved human gene symbols. See genelist/README.md for context.

Run:
    uv run python genelist/fetch_hgnc.py
    uv run python genelist/fetch_hgnc.py --all-loci   # keep non-coding too

Outputs:
    genelist/hgnc_protein_coding.tsv   raw upstream TSV (gitignored)
    genelist/hgnc_symbols.txt          one approved symbol per line
    genelist/hgnc_aliases.tsv          symbol  alias_or_previous
                                       (mapping table for normalisation)
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent

# Two slices of the HGNC dump; both are TSV with the same schema.
# Protein-coding only (~20K rows) is what TIMER3 / TCGA RSEM expression
# matrices effectively cover. The complete set (~43K) adds non-coding
# RNAs, pseudogenes, etc. — mostly absent from bulk RNA-seq.
_BASE = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv"
URLS = {
    "protein_coding": f"{_BASE}/locus_groups/protein-coding_gene.txt",
    "all": f"{_BASE}/hgnc_complete_set.txt",
}


def download(url: str, dest: Path) -> None:
    print(f"[download] {url}")
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())
    print(f"[download] wrote {dest} ({dest.stat().st_size/1024:.0f} KB)")


def parse(tsv: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """Returns (approved_symbols, [(symbol, alias_or_previous)])."""
    lines = tsv.read_text().splitlines()
    header = lines[0].split("\t")
    col = {name: i for i, name in enumerate(header)}
    sym_i = col["symbol"]
    status_i = col["status"]
    alias_i = col.get("alias_symbol")
    prev_i = col.get("prev_symbol")

    approved: list[str] = []
    aliases: list[tuple[str, str]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= sym_i:
            continue
        if parts[status_i] != "Approved":
            continue
        sym = parts[sym_i]
        if not sym:
            continue
        approved.append(sym)
        for col_i in (alias_i, prev_i):
            if col_i is None or col_i >= len(parts):
                continue
            raw = parts[col_i].strip().strip('"')
            if not raw:
                continue
            for a in raw.split("|"):
                a = a.strip()
                if a and a != sym:
                    aliases.append((sym, a))
    return approved, aliases


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all-loci", action="store_true",
        help="Use the full HGNC set (~43K including non-coding); default is "
             "protein-coding only (~20K, matches TIMER3/TCGA RSEM coverage).",
    )
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = "all" if args.all_loci else "protein_coding"
    raw = OUT_DIR / f"hgnc_{key}.tsv"
    download(URLS[key], raw)

    approved, aliases = parse(raw)
    sym_path = OUT_DIR / "hgnc_symbols.txt"
    sym_path.write_text("\n".join(sorted(set(approved))) + "\n")

    alias_path = OUT_DIR / "hgnc_aliases.tsv"
    seen: set[tuple[str, str]] = set()
    with alias_path.open("w") as f:
        f.write("symbol\talias\n")
        for sym, a in aliases:
            if (sym, a) in seen:
                continue
            seen.add((sym, a))
            f.write(f"{sym}\t{a}\n")

    print(f"\n[parse] approved symbols: {len(approved)} (unique {len(set(approved))})")
    print(f"[parse] alias/prev pairs: {len(aliases)} (unique {len(seen)})")
    print(f"[write] {sym_path}")
    print(f"[write] {alias_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
