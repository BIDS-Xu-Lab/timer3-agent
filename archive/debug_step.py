"""
Step-by-step debug: takes screenshots and dumps HTML at each stage.
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://compbio.top/timer3/"


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        page = await browser.new_page()

        # Monitor all Shiny-related XHR / WS activity
        requests_seen = []
        page.on("request", lambda r: requests_seen.append(r.url)
                if "sockjs" in r.url or "shiny" in r.url.lower() else None)

        print("Step 1: Loading page...")
        await page.goto(URL, wait_until="networkidle")
        await page.screenshot(path="step1_loaded.png")
        print("  -> step1_loaded.png")

        print("Step 2: Clicking Immune_Gene nav...")
        await page.click("#nav_Immune_Gene")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="step2_nav_clicked.png")
        print("  -> step2_nav_clicked.png")

        print("Step 3: Typing gene AAAS...")
        await page.click("#geneInput_gene-selectized")
        await page.fill("#geneInput_gene-selectized", "AAAS")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="step3_gene_typed.png")
        print("  -> step3_gene_typed.png")

        # Get visible dropdown options
        options = await page.evaluate("""
            () => Array.from(document.querySelectorAll(
                '.selectize-dropdown .option'
            )).map(o => ({value: o.dataset.value, text: o.textContent.trim()}))
        """)
        print(f"  Dropdown options for AAAS: {options[:5]}")

        if options:
            # Click first matching option
            first = options[0]
            opt_el = page.locator(f".selectize-dropdown .option[data-value='{first['value']}']").first
            await opt_el.click()
            await page.wait_for_timeout(500)
            print(f"  Selected: {first}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # Verify current gene value
        gene_val = await page.eval_on_selector(
            "#geneInput_gene",
            "el => el.value"
        )
        print(f"  Gene field value: {gene_val!r}")

        print("Step 4: Selecting BRCA...")
        await page.click("#Cancer_type_gene-selectized")
        await page.fill("#Cancer_type_gene-selectized", "BRCA")
        await page.wait_for_timeout(800)
        cancer_opts = await page.evaluate("""
            () => Array.from(document.querySelectorAll(
                '.selectize-dropdown .option'
            )).map(o => ({value: o.dataset.value, text: o.textContent.trim()}))
        """)
        print(f"  Cancer dropdown: {cancer_opts[:5]}")
        if cancer_opts:
            brca = next((o for o in cancer_opts if o['value'] == 'BRCA'), cancer_opts[0])
            await page.locator(f".selectize-dropdown .option[data-value='{brca['value']}']").first.click()
            await page.wait_for_timeout(400)
            print(f"  Selected cancer: {brca}")

        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # Verify cancer value
        cancer_val = await page.eval_on_selector(
            "#Cancer_type_gene",
            "el => Array.from(el.selectedOptions).map(o=>o.value)"
        )
        print(f"  Cancer field values: {cancer_val}")

        await page.screenshot(path="step4_form_filled.png")
        print("  -> step4_form_filled.png")

        print("Step 5: Clicking Submit...")
        # Check button is visible and enabled
        btn_info = await page.evaluate("""
            () => {
                const btn = document.querySelector('#geneInput_submit');
                return btn ? {exists: true, disabled: btn.disabled, visible: btn.offsetParent !== null} : {exists: false};
            }
        """)
        print(f"  Submit button: {btn_info}")

        await page.click("#geneInput_submit")
        await page.wait_for_timeout(2000)
        await page.screenshot(path="step5_submitted.png")
        print("  -> step5_submitted.png")

        print("Step 6: Waiting 30s and checking output...")
        for i in range(15):
            await asyncio.sleep(2)
            state = await page.evaluate("""
                () => {
                    const el = document.querySelector('#geneOutput_fixedHeatTable');
                    if (!el) return {found: false};
                    const recalc = el.classList.contains('recalculating');
                    const table = el.querySelector('table');
                    const rows = table ? table.querySelectorAll('tbody tr') : [];
                    return {
                        found: true,
                        recalculating: recalc,
                        hasTable: !!table,
                        rowCount: rows.length,
                        innerHTML_preview: el.innerHTML.substring(0, 300),
                    };
                }
            """)
            print(f"  t+{(i+1)*2}s: recalc={state.get('recalculating')} rows={state.get('rowCount')} hasTable={state.get('hasTable')}")
            if state.get("rowCount", 0) > 0:
                print("  SUCCESS! Rows found.")
                break

        await page.screenshot(path="step6_after_wait.png")
        print("  -> step6_after_wait.png")

        # Dump full output div
        full_html = await page.evaluate("""
            () => {
                const el = document.querySelector('#geneOutput_fixedHeatTable');
                return el ? el.innerHTML : 'NOT FOUND';
            }
        """)
        with open("debug_output_step6.html", "w") as f:
            f.write(full_html)
        print(f"  Full output HTML ({len(full_html)} chars) -> debug_output_step6.html")

        print(f"\nRequests seen: {len(requests_seen)}")

        input("\nPress Enter to close browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug())
