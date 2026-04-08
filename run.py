"""
Entry point: run Immune_Gene analysis and print results.

Usage:
    uv run python run.py
    uv run python run.py --genes AAAS 7SK --cancers ALL --show-browser
"""
import asyncio
import argparse
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


async def main(genes: list[str], cancers: str | list[str], headless: bool, debug_ws: bool = False):
    from timer3 import Timer3Client

    print(f"\nRunning TIMER3 Immune_Gene analysis")
    print(f"  Genes      : {genes}")
    print(f"  Cancer types: {cancers}")
    print(f"  Headless   : {headless}\n")

    async with Timer3Client(headless=headless) as client:
        result = await client.immune_gene(gene=genes[0])

    print(f"\n{'='*60}")
    print(f"Result: {result}")
    print(f"{'='*60}")

    if result.table:
        print(f"\nFirst 10 rows:\n")
        for i, row in enumerate(result.table[:10]):
            print(f"  {i+1:2d}. {json.dumps(row, ensure_ascii=False)}")
        if len(result.table) > 10:
            print(f"  ... ({len(result.table)} rows total)")
    else:
        print("\nNo table rows parsed. Saving raw HTML for inspection.")
        with open("debug_output.html", "w") as f:
            f.write(result.raw_html)
        print("  -> debug_output.html written")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--genes", nargs="+", default=["AAAS"])
    parser.add_argument("--cancers", nargs="+", default=["ALL"])
    parser.add_argument("--show-browser", action="store_true",
                        help="Run with visible browser window")
    parser.add_argument("--debug-ws", action="store_true",
                        help="Print all WebSocket frames for debugging")
    args = parser.parse_args()

    cancers = "ALL" if args.cancers == ["ALL"] else args.cancers
    asyncio.run(main(args.genes, cancers, headless=not args.show_browser, debug_ws=args.debug_ws))
