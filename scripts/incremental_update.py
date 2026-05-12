#!/usr/bin/env python3
"""Incremental update CLI for existing company data.

Usage:
    python scripts/incremental_update.py securitize.io
    python scripts/incremental_update.py --min-confidence 0.7 securitize.io ondo.finance
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from src.incremental import targeted_update


async def main():
    args = sys.argv[1:]

    # Handle help
    if not args or "--help" in args or "-h" in args:
        print("Usage: python scripts/incremental_update.py domain1.com domain2.com ...")
        print("\nExample:")
        print("  python scripts/incremental_update.py securitize.io ondo.finance")
        print("\nThis runs targeted extraction for high-value fields like:")
        print("  - Total funding")
        print("  - Revenue status")
        print("  - Employee count")
        print("  - AUM and client counts")
        sys.exit(0 if not args else 0)

    # Parse domains
    domains = []
    for arg in args:
        if arg.startswith("--"):
            print(f"Unknown option: {arg}")
            sys.exit(1)
        domains.append(arg)

    if not domains:
        print("Error: No domains specified")
        print("Usage: python scripts/incremental_update.py domain1.com domain2.com ...")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Targeted Update Mode")
    print(f"{'='*60}")
    print(f"  Companies: {len(domains)}")
    print(f"{'='*60}\n", flush=True)

    results = []
    for domain in domains:
        company_name = domain.replace(".", " ").title()
        print(f"Processing {company_name} ({domain})...", flush=True)

        result = await targeted_update(
            company_name=company_name,
            domain=domain,
        )
        results.append(result)

        # Print result
        if result["status"] == "completed":
            print(f"  ✓ Filled {result['fields_filled']}/{result['fields_requested']} fields", flush=True)
            print(f"    Cost: ${result['total_cost_usd']:.6f}, Time: {result['duration_secs']:.1f}s\n", flush=True)
        else:
            print(f"  ✗ Error: {result.get('error', 'Unknown')}\n", flush=True)

    # Summary
    print(f"{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status_symbol = "✓" if r["status"] == "completed" else "✗"
        print(f"  {status_symbol} {r['domain']:20s} | {r['status']:15s}", flush=True)

    total_cost = sum(r.get("total_cost_usd", 0) for r in results)
    print(f"\n  Total cost: ${total_cost:.6f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
