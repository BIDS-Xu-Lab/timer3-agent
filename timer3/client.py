"""
TIMER3 Playwright client.

Usage:
    import asyncio
    from timer3 import Timer3Client

    async def main():
        async with Timer3Client(headless=True) as client:
            result = await client.immune_gene(gene="AAAS")
            for row in result.table:
                print(row)

    asyncio.run(main())

Notes on TIMER3 Immune_Gene module:
  - Gene: single select (one gene at a time)
  - Cancer type: always ALL (the only option available in this module)
  - Results are a DataTable with rows = cancer types, cols = immune cell * algorithm
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import async_playwright, Browser, Page

from .selectize import selectize_type_and_click
from .parse_table import parse_fixed_heat_table

log = logging.getLogger(__name__)

TIMER3_URL = "https://compbio.top/timer3/"


@dataclass
class ImmuneGeneResult:
    gene: str
    raw_html: str = ""
    table: list[dict[str, Any]] = field(default_factory=list)

    def __repr__(self):
        return (
            f"ImmuneGeneResult(gene={self.gene!r}, rows={len(self.table)})"
        )


class Timer3Client:
    """
    Async context manager that manages a Playwright browser session for TIMER3.

        async with Timer3Client(headless=False) as client:
            result = await client.immune_gene("AAAS")
            print(result.table[0])
    """

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        return self

    async def __aexit__(self, *_):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def immune_gene(
        self,
        gene: str,
        purity_adj: bool = False,
        timeout: float = 120.0,
    ) -> "ImmuneGeneResult":
        """
        Run the Immune_Gene analysis on TIMER3 for a single gene.

        The module always uses ALL cancer types (the only available option).
        Results: correlation between the gene and each immune infiltrate,
                 across all cancer types and deconvolution algorithms.

        gene      : gene symbol, e.g. "AAAS" or "TP53"
        purity_adj: enable tumor purity adjustment
        timeout   : seconds to wait for the result (usually 5-15s)
        """
        page = self._page

        # ---- 1. Navigate to page ----------------------------------------
        log.info("Loading TIMER3...")
        await page.goto(TIMER3_URL, wait_until="networkidle", timeout=30000)

        # ---- 2. Click Immune_Gene nav button ----------------------------
        log.info("Navigating to Immune_Gene module...")
        await page.click("#nav_Immune_Gene")
        await page.wait_for_timeout(800)

        # ---- 3. Select gene (type-and-click approach) -------------------
        log.info(f"Selecting gene: {gene!r}")
        await selectize_type_and_click(page, "geneInput_gene", gene)

        # ---- 4. Cancer type is always ALL (only option available) -------
        # No action needed — the field defaults to ALL

        # ---- 5. Purity adjustment (optional) ----------------------------
        if purity_adj:
            await page.check("#geneInput_purityadj")

        # ---- 6. Submit --------------------------------------------------
        log.info("Submitting...")
        await page.click("#geneInput_submit")

        # ---- 7. Wait for results in DOM ---------------------------------
        log.info(f"Waiting up to {timeout}s for results...")
        raw_html = await _wait_for_datatable(
            page,
            container_selector="#geneOutput_fixedHeatTable",
            timeout=timeout,
        )

        # ---- 8. Parse ---------------------------------------------------
        table = parse_fixed_heat_table(raw_html)
        log.info(f"Done. Got {len(table)} rows.")

        return ImmuneGeneResult(gene=gene, raw_html=raw_html, table=table)


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

async def _wait_for_datatable(
    page: Page,
    container_selector: str,
    timeout: float,
    poll_interval: float = 1.5,
) -> str:
    """
    Poll until the DataTable inside `container_selector` has tbody rows.
    Returns the outerHTML of the scrollBody table.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    last_log = 0.0

    while asyncio.get_event_loop().time() < deadline:
        state: dict = await page.evaluate(
            """
            (selector) => {
                const el = document.querySelector(selector);
                if (!el) return {found: false};
                // DataTables renders two tables: a header clone and the real body table.
                // Use querySelectorAll to count ALL tbody > tr.
                const rows = el.querySelectorAll('tbody tr');
                const bodyTable = el.querySelector('.dataTables_scrollBody table');
                return {
                    found: true,
                    rowCount: rows.length,
                    tableHTML: bodyTable ? bodyTable.outerHTML : '',
                };
            }
            """,
            container_selector,
        )

        if state.get("found") and state.get("rowCount", 0) > 0:
            log.info(f"  Ready: {state['rowCount']} rows")
            return state["tableHTML"]

        now = asyncio.get_event_loop().time()
        if now - last_log > 5:
            elapsed = now - (deadline - timeout)
            log.info(
                f"  ... waiting ({elapsed:.0f}s elapsed, "
                f"rows={state.get('rowCount', 0)})"
            )
            last_log = now

        await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f"DataTable in '{container_selector}' did not populate within {timeout}s"
    )
