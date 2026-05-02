# timer3-agent

Two ways to query TIMER3-style gene/immune correlations:

1. **`timer3/`** — a Playwright client that scrapes the live [TIMER3](https://compbio.top/timer3/) website. Use when you need exact TIMER3 numbers (all 11+ algorithms, purity adjustment, every column the web UI shows).
2. **`reproduce/`** — an offline lookup that precomputes Spearman correlations from public data (UCSC Xena pan-cancer expression + TIMER3's published `infiltration_estimation_for_tcga.csv`). Returns answers in milliseconds and exposes both a Python API and an HTTP server. Covers 7 of the 11 algorithms (the 4 not in the public CSV — ABIS, CONSENSUS_TME, ImmuCellAI, TIDE — are unavailable). Validated to **Pearson 0.91** vs the live site across 20 reference genes × 7200 cells.

The Immune_Gene module — Spearman correlations between a gene's expression and immune cell infiltration across all TCGA cancer types and deconvolution algorithms — is the focus of both implementations.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone https://github.com/BIDS-Xu-Lab/timer3-agent.git
cd timer3-agent

# Install dependencies
uv sync

# Install Chromium (one-time)
uv run playwright install chromium
```

## Quick Start

### Command line

```bash
# Query a single gene (headless by default)
uv run python run.py --genes TP53

# Show the browser window while running
uv run python run.py --genes AAAS --show-browser
```

### Python API

```python
import asyncio
from timer3 import Timer3Client

async def main():
    async with Timer3Client(headless=True) as client:
        result = await client.immune_gene(gene="TP53")

    print(result)
    # ImmuneGeneResult(gene='TP53', rows=41)

    # result.table is a list of dicts — one row per cancer type
    for row in result.table:
        cancer = row["cancer"]
        cd8_timer = row["T cell CD8+\nTIMER"]
        print(f"{cancer:25s}  CD8+ (TIMER) = {cd8_timer}")

asyncio.run(main())
```

Example output:

```
ACC (n=79)                CD8+ (TIMER) = 0.197
BLCA (n=406)              CD8+ (TIMER) = 0.106
BRCA (n=1086)             CD8+ (TIMER) = -0.029
...
```

### Batch queries

```python
import asyncio, json
from timer3 import Timer3Client

GENES = ["TP53", "AAAS", "EGFR", "KRAS"]

async def batch():
    results = {}
    async with Timer3Client(headless=True) as client:
        for gene in GENES:
            result = await client.immune_gene(gene=gene)
            results[gene] = result.table
            print(f"{gene}: {len(result.table)} rows")

    with open("output.json", "w") as f:
        json.dump(results, f, indent=2)

asyncio.run(batch())
```

## Output Format

`result.table` is a `list[dict]` where:

| Field | Description |
|-------|-------------|
| `cancer` | Cancer type and sample size, e.g. `"BRCA (n=1086)"` |
| `"T cell CD8+\nTIMER"` | Spearman r for CD8+ T cells estimated by TIMER |
| `"T cell CD8+\nEPIC"` | Spearman r estimated by EPIC |
| `"T cell CD8+\nCIBERSORT"` | Spearman r estimated by CIBERSORT |
| ... | One column per immune cell × algorithm combination |

Values are correlation coefficients (strings); `"NA"` when not applicable.

`result.raw_html` contains the original DataTable HTML if you need to re-parse.

## API Reference

```python
Timer3Client(headless: bool = True)
```

| Method | Parameters | Returns |
|--------|-----------|---------|
| `immune_gene` | `gene: str`, `purity_adj: bool = False`, `timeout: float = 120.0` | `ImmuneGeneResult` |

- `purity_adj`: enable tumor purity adjustment for the correlation
- `timeout`: seconds to wait for the server response (typically 5–15 s)

## How It Works

TIMER3 is an R Shiny application that communicates over WebSocket (SockJS). This client uses Playwright to:

1. Navigate to the Immune_Gene module
2. Select a gene via the Selectize dropdown (type-and-click)
3. Click Submit — cancer type is always ALL (the only available option)
4. Poll the DOM until the DataTables result table is populated
5. Parse the HTML table into a list of Python dicts

## Notes

- Each `immune_gene()` call reloads the page. For batch queries, reuse the same `Timer3Client` context to avoid re-launching the browser each time.
- Results are returned in ~5–15 seconds depending on server load.
- The `archive/` directory contains debug scripts and screenshots used during development.

---

# Local lookup (`reproduce/`)

Offline replica that answers gene/immune-correlation queries in ~1 ms. Covers **20530 genes × 36 cancer labels × 119 immune features** (7 deconvolution algorithms: TIMER, CIBERSORT, CIBERSORT-ABS, EPIC, MCPCOUNTER, QUANTISEQ, XCELL). BRCA is split into Basal/Her2/LumA/LumB subtypes, mirroring TIMER3.

## One-time setup

```bash
# 1. Get the published infiltration matrix (~10 MB)
curl -L -o ~/Downloads/infiltration_estimation_for_tcga.csv.gz \
  "https://compbio.top/timer3/infiltration_estimation_for_tcga.csv.gz"
gunzip ~/Downloads/infiltration_estimation_for_tcga.csv.gz

# 2. Get UCSC Xena pan-cancer expression + phenotype + subtypes (~330 MB)
mkdir -p data/raw && cd data/raw
curl -L -o expression_pancan.tsv.gz \
  "https://pancanatlas.xenahubs.net/download/EB%2B%2BAdjustPANCAN_IlluminaHiSeq_RNASeqV2.geneExp.xena.gz"
curl -L -o phenotype.tsv.gz \
  "https://pancanatlas.xenahubs.net/download/TCGA_phenotype_denseDataOnlyDownload.tsv.gz"
curl -L -o subtype.tsv.gz \
  "https://pancanatlas.xenahubs.net/download/TCGASubtype.20170308.tsv.gz"
gunzip phenotype.tsv.gz subtype.tsv.gz
cd ../..

# 3. Build the lookup index (~50 s, produces data/lookup.npz, ~300 MB)
uv run python -m reproduce.build_index
```

## Python usage

```python
from reproduce.api import LocalTimer3
api = LocalTimer3()                                       # ~1 s to load 300 MB index

# Full table for one gene: 36 cancers × 119 features = 4284 rows
df = api.gene("EGFR")

# One cancer
df = api.gene("EGFR", cancer="BRCA-LumA")                 # 119 rows

# All Macrophage features across all cancers
df = api.gene("EGFR", feature_substr="Macrophage")        # 504 rows

# Top features by |rho| in one cancer
df = api.gene("EGFR", cancer="BRCA-LumA")
top10 = df.reindex(df["rho"].abs().sort_values(ascending=False).index).head(10)
```

Each call returns a pandas DataFrame with columns `cancer | feature | n | rho`.

Example — top 5 features correlated with EGFR in BRCA-LumA (n=564):

```
                                feature       rho
                  T cell CD4+ Th1_XCELL -0.651
            Endothelial cell_MCPCOUNTER  0.629
              uncharacterized cell_EPIC -0.591
                      T cell CD8+_TIMER  0.584
      Myeloid dendritic cell_MCPCOUNTER  0.566
```

## HTTP API

```bash
uv run uvicorn reproduce.server:app --port 8080
```

| Endpoint | Description |
|---|---|
| `GET /` | service metadata |
| `GET /cancers` | 36 cancer labels with sample counts |
| `GET /features` | 119 immune-feature column names |
| `GET /genes?prefix=EG&limit=20` | gene autocomplete |
| `GET /gene/{symbol}` | full table |
| `GET /gene/{symbol}?cancer=BRCA-LumA` | filter to one cancer |
| `GET /gene/{symbol}?feature_substr=Macrophage` | substring filter on feature |
| `GET /gene/{symbol}?top=10` | top-N rows by \|rho\| |
| `GET /gene/{symbol}?format=wide` | pivot to cancer × feature wide table |

Auto-generated OpenAPI docs at http://localhost:8080/docs.

```bash
curl "http://localhost:8080/gene/EGFR?cancer=BRCA-LumA&top=5"
# [{"cancer":"BRCA-LumA","feature":"T cell CD4+ Th1_XCELL","n":564,"rho":-0.6511}, ...]
```

## Validation against the live site

`reproduce/scrape_golden.py` scrapes 20 reference genes (TP53, EGFR, KRAS, MYC, BRAF, PIK3CA, PTEN, RB1, BRCA1, APC, CD8A, FOXP3, IFNG, GZMB, PDCD1, CD274, CTLA4, ACTB, GAPDH, AAAS) from the live TIMER3 site as a golden-standard dataset. `reproduce/benchmark.py` joins those scrapes against the local index.

```bash
uv run python -m reproduce.scrape_golden    # ~5–7 min, one-time
uv run python -m reproduce.benchmark
```

Headline fidelity (20 genes × 36 cancers × 7 algorithms = 7200 cells; 3800 cells where local sample-size matches TIMER3 exactly):

- Pearson(local, scraped) = **0.91**
- Median \|diff\| = **0.06**, P95 = 0.24
- 71 % of cells within ±0.10 of TIMER3's number

Per algorithm (cells with matching n):

| Algorithm | Pearson | mean \|diff\| |
|---|---|---|
| MCPCOUNTER | 0.96 | 0.07 |
| QUANTISEQ | 0.96 | 0.07 |
| CIBERSORT | 0.95 | 0.07 |
| CIBERSORT-ABS | 0.95 | 0.07 |
| XCELL | 0.92 | 0.08 |
| EPIC | 0.84 | 0.10 |
| TIMER | 0.72 | 0.14 |

## Known limitations

- **4 algorithms unavailable**: ABIS, CONSENSUS_TME, ImmuCellAI, TIDE are not in the public infiltration CSV.
- **Plain Spearman only**: TIMER3 defaults to purity-adjusted partial Spearman; the per-sample purity vector isn't published, so this implementation reports plain Spearman.
- **Sample-set drift for GBM/OV**: Xena's RSEM RNAseq matrix excludes some legacy samples that TIMER3 includes (GBM 153 vs 287; OV 302 vs 422). Other cancers match within 1–7 samples.
- **Expression normalization**: Xena uses batch-corrected log2(norm_count+1); TIMER3 uses GDAC Firehose RSEM TPM. Spearman is rank-based so the difference is small in big cohorts but visible (~0.1) in small ones (DLBC n=48, KICH n=66).
- **Low-variance genes are unreliable**: housekeeping genes (ACTB, GAPDH) and uncharacterized loci (AAAS) have unstable Spearman because the rank order is dominated by noise. This is a property of Spearman, not a bug.

