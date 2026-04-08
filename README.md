# timer3-agent

A Python automation client for [TIMER3](https://compbio.top/timer3/) built with [Playwright](https://playwright.dev/python/). Automates browser interactions and extracts structured data from TIMER3's web interface — useful when you need to query many genes programmatically without manual clicking.

Currently supports the **Immune_Gene** module, which returns Spearman correlations between a gene's expression and immune cell infiltration across all TCGA cancer types and deconvolution algorithms.

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
