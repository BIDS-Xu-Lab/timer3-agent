# Gene-symbol reference list

This folder downloads a canonical list of human gene symbols from **HGNC**
(HUGO Gene Nomenclature Committee) — the official body that approves human
gene names. We use it as the *reference whitelist* for any code in this
repo that needs to validate, autocomplete, or normalize a user-supplied
gene query.

## Why HGNC, not TIMER3?

TIMER3's web UI exposes its gene list only through a server-side
autocomplete (Shiny `server=TRUE`), so enumerating it requires sweeping
~1300 letter prefixes against the live site (~22 min, fragile, subject
to rate limiting). HGNC ships the full table as a single static TSV, is
the upstream source of truth, and includes alias / previous-symbol
mappings that TIMER3 does not. The set of genes TIMER3 actually has data
for is approximately a subset of HGNC's protein-coding genes (see
"Coverage notes" below) — close enough that the upside of scraping
TIMER3 is small.

## Usage

```bash
# protein-coding genes only (~19K rows, what TIMER3/TCGA RSEM cover)
uv run python genelist/fetch_hgnc.py

# full HGNC set (~43K, includes lncRNA, pseudogenes, miRNA, etc.)
uv run python genelist/fetch_hgnc.py --all-loci
```

Outputs (all under `genelist/`):

| File | Description |
|---|---|
| `hgnc_protein_coding.tsv` (or `hgnc_all.tsv`) | raw upstream TSV — gitignored |
| `hgnc_symbols.txt` | one approved symbol per line, sorted |
| `hgnc_aliases.tsv` | `symbol \t alias_or_previous` mapping for normalization |

## Source

Authoritative download (HGNC moved off EBI FTP; the canonical mirror is
now Google Cloud Storage):

- protein-coding: https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/locus_groups/protein-coding_gene.txt
- complete set:   https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt

Both files are updated frequently (current count: **19,273** approved
protein-coding symbols, ~43K total).

## Coverage notes (vs the local TIMER3 index)

Cross-checked against `data/lookup.npz` (20,530 row IDs from UCSC Xena's
PANCAN expression matrix):

| Set | Count |
|---|---|
| HGNC protein-coding | 19,273 |
| Local index (Xena) | 20,530 |
| **Intersection** | **16,274** (84% of HGNC) |
| HGNC only (no expression in our index) | 2,999 |
| Local only (Entrez IDs + retired symbols) | 4,256 |

The "local only" 4256 are mostly numeric Entrez IDs (e.g. `100130426`,
`10357`) that Xena ships for genes lacking a current HUGO symbol, plus
retired symbols (e.g. `MLL` instead of `KMT2A`). Use `hgnc_aliases.tsv`
to normalize those before lookup.

## Next steps (deferred)

- If we ever need TIMER3's *exact* gene list (e.g. for a strict
  validation pass), `git log` has a working Selectize-prefix sweep —
  resurrect it then.
- Symbol-aliasing in the API: load `hgnc_aliases.tsv` at startup so
  `api.gene("MLL")` redirects to `KMT2A` automatically. Not implemented
  yet because the local index already accepts the most common forms.
