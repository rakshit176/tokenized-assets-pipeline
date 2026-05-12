#!/usr/bin/env python3
"""Validate extracted company data files.

Usage:
    python scripts/validate_output.py output/securitize_io.json
    python scripts/validate_output.py output/*.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.validation import validate_company_data


def validate_file(file_path: str) -> dict:
    """Validate a single JSON file."""
    with open(file_path) as f:
        data = json.load(f)

    # Get the actual data section
    if "data" in data:
        data = data["data"]

    errors = validate_company_data(data)

    total_errors = sum(len(e) for e in errors.values())

    return {
        "file": file_path,
        "total_errors": total_errors,
        "tables_with_errors": len(errors),
        "errors": errors,
    }


def main():
    args = sys.argv[1:]

    if not args:
        print("Usage: python scripts/validate_output.py file1.json file2.json ...")
        print("\nValidates extracted company data for:")
        print("  - URL format")
        print("  - Year ranges (1990-current)")
        print("  - Funding amount ranges")
        print("  - Employee count ranges")
        print("  - Status enum values")
        sys.exit(1)

    import glob
    files = []
    for arg in args:
        if "*" in arg:
            files.extend(glob.glob(arg))
        else:
            files.append(arg)

    print(f"\nValidating {len(files)} file(s)...\n")

    all_results = []
    for f in files:
        try:
            result = validate_file(f)
            all_results.append(result)

            # Print summary for this file
            status = "✓ PASS" if result["total_errors"] == 0 else "✗ FAIL"
            print(f"{status} {f}: {result['total_errors']} errors")

            if result["errors"]:
                for table, errs in result["errors"].items():
                    print(f"  {table}:")
                    for err in errs[:3]:
                        print(f"    - {err}")
                    if len(errs) > 3:
                        print(f"    ... and {len(errs) - 3} more")

        except Exception as e:
            print(f"✗ ERROR {f}: {e}")

    # Overall summary
    total_errors = sum(r["total_errors"] for r in all_results)
    passed = sum(1 for r in all_results if r["total_errors"] == 0)

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {passed}/{len(all_results)} files passed")
    if total_errors > 0:
        print(f"  Total errors: {total_errors}")
    print(f"{'='*60}")

    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
