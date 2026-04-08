"""
DOM exploration script - discovers actual Shiny input IDs and WebSocket message format.
Run once to understand the page structure before using the main client.
"""
import asyncio
import json
from playwright.async_api import async_playwright


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Collect all WebSocket frames
        ws_messages = []

        def on_websocket(ws):
            print(f"[WS] Connected: {ws.url}")

            def on_frame(frame):
                try:
                    data = json.loads(frame.payload)
                    ws_messages.append(data)
                    # Only print frames that have values (i.e., output responses)
                    if "values" in data and data["values"]:
                        print(f"\n[WS RESPONSE] keys in values: {list(data['values'].keys())}")
                        for k, v in data["values"].items():
                            if isinstance(v, str) and len(v) > 100:
                                print(f"  {k}: <string len={len(v)}>")
                            else:
                                print(f"  {k}: {v}")
                except Exception:
                    pass

            ws.on("framereceived", on_frame)

        page.on("websocket", on_websocket)

        print("Navigating to TIMER3...")
        await page.goto("https://compbio.top/timer3/", wait_until="networkidle")

        # Dump all input/select IDs on the page
        inputs = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('input, select, button, [id]');
                return Array.from(els).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    name: el.name,
                    type: el.type,
                    class: el.className.substring(0, 60)
                })).filter(e => e.id);
            }
        """)
        print("\n=== ALL ELEMENTS WITH IDs ===")
        for el in inputs:
            print(f"  <{el['tag']}> id={el['id']!r} type={el.get('type','')} class={el['class'][:40]}")

        # Click the Immune tab
        print("\nLooking for Immune_Gene tab...")
        await page.click("text=Immune", timeout=5000)
        await page.wait_for_timeout(1000)

        # Re-dump after tab click
        inputs2 = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('input, select, button, [id]');
                return Array.from(els).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    name: el.name,
                })).filter(e => e.id && e.id.length > 0);
            }
        """)
        print("\n=== ALL IDs AFTER CLICKING IMMUNE ===")
        for el in inputs2:
            print(f"  <{el['tag']}> id={el['id']!r}")

        print("\n[Explorer] Browser stays open - inspect manually, then close.")
        await asyncio.sleep(60)
        await browser.close()

        print(f"\n=== CAPTURED {len(ws_messages)} WS MESSAGES ===")
        for i, msg in enumerate(ws_messages[:10]):
            print(f"\n--- Message {i} ---")
            print(json.dumps(msg, indent=2)[:500])


if __name__ == "__main__":
    asyncio.run(explore())
