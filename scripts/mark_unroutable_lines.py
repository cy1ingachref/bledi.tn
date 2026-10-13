#!/usr/bin/env python3
"""Mark seed lines that can never be routed with an explicit `routable: false`.

Why this exists
---------------
The BizerteConnect API publishes no stops endpoint (`bus-stops/`,
`bus-stations/`, `stops/`, `stations/` and `bus-trips/` all 404; `/trips/` and
`/season-schedules/` need admin auth). Its 117 imported lines therefore carry
named endpoints, outbound/return schedules and an `external_id`, but an EMPTY
`stations` array and no coordinates.

A line with no stops is not a graph edge, so those 117 lines are permanently
unroutable. They are still worth keeping: the schedules and the Arabic/Latin
destination names are useful for the UI. What they must not be is *silently*
unroutable, which is what
`services/transit/tests/test_seed_integrity.py::test_no_line_with_fewer_than_two_valid_stops`
exists to catch.

This script makes the distinction explicit and machine-checkable, so the test
can assert "nothing is unroutable unless it says so" instead of being weakened
to ignore a hardcoded id prefix.

Usage
-----
    python scripts/mark_unroutable_lines.py            # report only
    python scripts/mark_unroutable_lines.py --write    # rewrite the seed

Idempotent: re-running reports `0 changed` once the markers are in place.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"

# The only source that currently publishes lines without stops.
UNROUTABLE_SOURCE = "bizerteconnect-api"
UNROUTABLE_REASON = (
    "BizerteConnect publishes no stops endpoint; these lines carry named "
    "endpoints and schedules but no stops and no coordinates, so they are not "
    "graph edges."
)


def stop_count(line: dict, station_ids: set[str]) -> int:
    stops = line.get("stations") or line.get("stops") or []
    return len([s for s in stops if s in station_ids])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="rewrite the seed in place")
    args = ap.parse_args()

    if not SEED.exists():
        print(f"seed not found: {SEED}", file=sys.stderr)
        return 1

    with SEED.open(encoding="utf-8") as f:
        data = json.load(f)

    stations = {s["id"] for s in data.get("stations", []) if s.get("id")}
    lines = data.get("lines", [])

    changed = 0
    unroutable_ids: list[str] = []
    by_source: Counter[str] = Counter()

    for line in lines:
        n_stops = stop_count(line, stations)
        # A line is unroutable when it has fewer than 2 resolvable stops. That is
        # the actual graph requirement, so it is the condition we key on rather
        # than the id prefix -- a future import that drops stops from some other
        # source is caught by the same rule.
        should_be_unroutable = n_stops < 2

        if should_be_unroutable:
            unroutable_ids.append(str(line.get("id", "?")))
            by_source[str(line.get("source", "unknown"))] += 1
            if line.get("routable") is not False:
                line["routable"] = False
                changed += 1
        else:
            # Routable lines may carry the key explicitly, but never `false`.
            if line.get("routable") is False:
                line["routable"] = True
                changed += 1

    # Keep the metadata honest about what was marked and why.
    meta = data.setdefault("metadata", {})
    meta["unroutable_lines"] = {
        "count": len(unroutable_ids),
        "reason": UNROUTABLE_REASON,
        "sources": dict(by_source),
    }

    print(f"lines total            : {len(lines)}")
    print(f"unroutable (<2 stops)  : {len(unroutable_ids)}")
    print(f"  by source            : {dict(by_source)}")
    print(f"markers changed        : {changed}")

    if not args.write:
        print("\n(dry run; pass --write to save)")
        return 0

    SEED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
