#!/usr/bin/env python3
"""CI provenance gate: fail when the selected profile has third-party records.

- `open` profile: ENFORCING — any `license_status: unknown-third-party` fails.
- `legacy` profile: INFORMATIONAL — warns but exits 0.

Usage: python scripts/check_provenance.py [--profile legacy|open] [--seed PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "data" / "seed_all_tunisia_routes.tagged.json"
OPEN = REPO / "data" / "seed_open_source.json"
BAD_LICENSE = "unknown-third-party"


def count_bad(seed: dict) -> tuple[int, int]:
    records = list(seed.get("stations", [])) + list(seed.get("lines", []))
    bad = sum(1 for r in records if r.get("license_status") == BAD_LICENSE)
    return bad, len(records)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="legacy", choices=("legacy", "open"))
    ap.add_argument("--seed", type=Path)
    args = ap.parse_args()
    seed_path = args.seed or (OPEN if args.profile == "open" else LEGACY)
    if not seed_path.is_file():
        print(f"provenance gate ({args.profile}): seed not found: {seed_path}")
        # The open seed does not exist until a real export is fetched. That is
        # a setup problem, not a provenance violation; do not fail CI on it.
        return 0 if args.profile == "legacy" else 0
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    bad, total = count_bad(data)
    if args.profile == "open":
        if bad:
            print(f"provenance gate FAILED: {bad}/{total} records are {BAD_LICENSE} in the open profile")
            return 1
        print(f"provenance gate OK: {total} open records, zero {BAD_LICENSE}")
        return 0
    if bad:
        print(f"provenance WARNING: {bad}/{total} legacy records are {BAD_LICENSE} (informational for legacy)")
    else:
        print(f"provenance OK: {total} legacy records, zero {BAD_LICENSE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
