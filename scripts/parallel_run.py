#!/usr/bin/env python3
"""Run the extraction pipeline on multiple companies in parallel.

Usage:
    python scripts/parallel_run.py company1.com company2.com company3.com
    python scripts/parallel_run.py --max-concurrent 2 company1.com company2.com

Processes multiple companies concurrently using asyncio with configurable concurrency.
"""
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


async def run_company(domain: str, idx: int, total: int) -> dict[str, Any]:
    """Run the pipeline for a single company."""
    from step_run import run_company

    print(f"\n[{idx}/{total}] Starting {domain}...", flush=True)
    start = time.time()

    try:
        result = await run_company(domain.title().replace(".", " "), domain)
        elapsed = time.time() - start
        print(f"[{idx}/{total}] Completed {domain} in {elapsed:.1f}s", flush=True)
        return result
    except Exception as e:
        elapsed = time.time() - start
        print(f"[{idx}/{total}] FAILED {domain} after {elapsed:.1f}s: {e}", flush=True)
        return {
            "company": domain.title().replace(".", " "),
            "domain": domain,
            "error": str(e),
            "fill_rate": 0,
            "real_fill": 0,
            "total_cost_usd": 0,
            "timing": {"total": elapsed},
        }


async def main():
    args = sys.argv[1:]

    # Handle help
    if not args or "--help" in args or "-h" in args:
        print("Usage: python scripts/parallel_run.py [--max-concurrent N] domain1.com domain2.com ...")
        print("\nExample:")
        print("  python scripts/parallel_run.py securitize.io ondo.finance centrifuge.io")
        print("  python scripts/parallel_run.py --max-concurrent 2 securitize.io ondo.finance")
        print("\nOptions:")
        print("  --max-concurrent N    Maximum number of concurrent jobs (default: 3)")
        sys.exit(0 if not args else 0)

    # Parse options
    max_concurrent = 3
    domains = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--max-concurrent" and i + 1 < len(args):
            max_concurrent = int(args[i + 1])
            i += 2
        else:
            if arg.startswith("--"):
                print(f"Unknown option: {arg}")
                sys.exit(1)
            domains.append(arg)
            i += 1

    if not domains:
        print("Error: No domains specified")
        print("Usage: python scripts/parallel_run.py [--max-concurrent N] domain1.com domain2.com ...")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Parallel Pipeline Runner")
    print(f"{'='*60}")
    print(f"  Companies: {len(domains)}")
    print(f"  Max concurrent: {max_concurrent}")
    print(f"{'='*60}\n", flush=True)

    t0 = time.time()

    # Process with semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_limit(domain: str, idx: int):
        async with semaphore:
            return await run_company(domain, idx, len(domains))

    tasks = [process_with_limit(d, i + 1) for i, d in enumerate(domains)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions in results
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            print(f"Error: {r}", flush=True)
        else:
            processed_results.append(r)

    elapsed = time.time() - t0

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY: {len(processed_results)} companies in {elapsed:.1f}s")
    print(f"  Average: {elapsed / len(processed_results):.1f}s per company")
    print(f"{'='*60}")
    for r in processed_results:
        if "error" in r:
            print(f"  {r.get('domain', 'unknown'):20s} | FAILED: {r['error'][:40]}", flush=True)
        else:
            print(f"  {r['company']:20s} | Fill={r['fill_rate']:5.1f}% Real={r['real_fill']:5.1f}% "
                  f"Cost=${r['total_cost_usd']:.4f} Time={r['timing']['total']:.1f}s", flush=True)

    # Cache stats
    try:
        from src.cache import get_cache
        cache = get_cache()
        stats = cache.stats()
        if stats["hits"] + stats["misses"] > 0:
            print(f"\n  Cache: {stats['hits']} hits, {stats['misses']} misses, {stats['hit_rate']} hit rate", flush=True)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
