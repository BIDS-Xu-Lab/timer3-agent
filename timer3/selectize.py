"""
Helpers for interacting with Selectize.js dropdowns in Playwright.
Uses the click-based approach (type text, click dropdown option)
which reliably triggers Shiny's input bindings.
"""
import asyncio
import logging
from playwright.async_api import Page

log = logging.getLogger(__name__)


async def selectize_type_and_click(page: Page, select_id: str, value: str):
    """
    Select a value from a Selectize dropdown by typing and clicking.
    This is the most reliable approach as it properly triggers all Shiny events.

    select_id : the original <select> element's id (e.g. 'geneInput_gene')
    value     : the option value to select (must exist in the dropdown)
    """
    text_input = page.locator(f"#{select_id}-selectized")
    await text_input.click()
    await text_input.fill(value)
    await page.wait_for_timeout(600)

    # Click the matching option in the open dropdown
    option = page.locator(
        f".selectize-dropdown[style*='display: block'] .option[data-value='{value}']"
    ).first
    try:
        await option.wait_for(state="visible", timeout=5000)
        await option.click()
        log.debug(f"  selectize: selected '{value}' in #{select_id}")
    except Exception:
        # Fallback: just press Enter to select the first match
        log.warning(f"  selectize: exact option not found for '{value}', pressing Enter")
        await text_input.press("Enter")

    await asyncio.sleep(0.3)
