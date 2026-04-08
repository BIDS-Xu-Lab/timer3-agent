"""
Targeted debug: check Shiny input state and output HTML after submit.
"""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://compbio.top/timer3/"


async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()

        await page.goto(URL, wait_until="networkidle")
        await page.click("#nav_Immune_Gene")
        await page.wait_for_timeout(1000)

        # Check default state of ALL inputs
        defaults = await page.evaluate("""
            () => ({
                gene: document.querySelector('#geneInput_gene')?.value,
                cancers: Array.from(document.querySelector('#Cancer_type_gene')?.selectedOptions || []).map(o=>o.value),
                cancer_opts_count: document.querySelector('#Cancer_type_gene')?.options.length,
            })
        """)
        print(f"Default state: {json.dumps(defaults)}")

        # --- Strategy: use the click approach for gene ---
        print("\nClicking gene input and typing AAAS...")
        gene_input = page.locator("#geneInput_gene-selectized")
        await gene_input.click()
        await gene_input.fill("AAAS")
        await page.wait_for_timeout(800)

        # Find the gene option (within the gene selectize dropdown specifically)
        opt = await page.evaluate("""
            () => {
                // Find any open selectize dropdown with an AAAS option
                const drops = document.querySelectorAll('.selectize-dropdown[style*="display: block"]');
                for (const drop of drops) {
                    const opt = drop.querySelector('.option[data-value="AAAS"]');
                    if (opt) return {found: true, text: opt.textContent};
                }
                return {found: false};
            }
        """)
        print(f"Gene dropdown AAAS option: {opt}")

        await page.click(".selectize-dropdown .option[data-value='AAAS']")
        await page.wait_for_timeout(300)

        gene_val = await page.eval_on_selector("#geneInput_gene", "el => el.value")
        print(f"Gene value after selection: {gene_val!r}")

        # Check default cancer types (don't change them)
        cancer_vals = await page.eval_on_selector(
            "#Cancer_type_gene",
            "el => Array.from(el.selectedOptions).map(o => o.value)"
        )
        print(f"Cancer values (unchanged default): {cancer_vals}")

        # Check Shiny's view of the inputs
        shiny_state = await page.evaluate("""
            () => {
                if (typeof Shiny === 'undefined') return {error: 'Shiny not loaded'};
                return {
                    gene: Shiny.shinyapp?.$inputValues?.geneInput_gene,
                    cancers: Shiny.shinyapp?.$inputValues?.Cancer_type_gene,
                    submitCount: Shiny.shinyapp?.$inputValues?.geneInput_submit,
                };
            }
        """)
        print(f"Shiny input state before submit: {json.dumps(shiny_state)}")

        await page.screenshot(path="inspect_before_submit.png")

        print("\nClicking submit...")
        await page.click("#geneInput_submit")
        await page.wait_for_timeout(2000)

        shiny_state_after = await page.evaluate("""
            () => {
                if (typeof Shiny === 'undefined') return {};
                return {
                    gene: Shiny.shinyapp?.$inputValues?.geneInput_gene,
                    cancers: Shiny.shinyapp?.$inputValues?.Cancer_type_gene,
                    submitCount: Shiny.shinyapp?.$inputValues?.geneInput_submit,
                };
            }
        """)
        print(f"Shiny input state after submit: {json.dumps(shiny_state_after)}")

        # Poll and dump output
        for i in range(20):
            await asyncio.sleep(2)
            state = await page.evaluate("""
                () => {
                    const el = document.querySelector('#geneOutput_fixedHeatTable');
                    if (!el) return {found: false};
                    const recalc = el.classList.contains('recalculating');
                    const rows = el.querySelectorAll('tbody tr');
                    return {
                        found: true,
                        recalculating: recalc,
                        rowCount: rows.length,
                        classList: el.className,
                        innerHTMLLen: el.innerHTML.length,
                        preview: el.innerHTML.substring(0, 500),
                    };
                }
            """)
            print(f"  t+{(i+1)*2}s: recalc={state.get('recalculating')} rows={state.get('rowCount')} htmlLen={state.get('innerHTMLLen')}")
            if state.get("rowCount", 0) > 0:
                print("  SUCCESS!")
                break
            if i == 4:  # at t=10, dump the preview
                print(f"\n  HTML preview at t=10s:\n{state.get('preview', '')[:400]}\n")

        await page.screenshot(path="inspect_after_wait.png")
        print("Screenshots saved.")

        # Dump full HTML
        full = await page.eval_on_selector("#geneOutput_fixedHeatTable", "el => el.innerHTML")
        with open("inspect_output.html", "w") as f:
            f.write(full)
        print(f"HTML ({len(full)} chars) -> inspect_output.html")

        input("\nPress Enter to close...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug())
