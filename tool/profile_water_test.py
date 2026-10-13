#!/usr/bin/env python3
"""Time the water test over all stops, to find the bottleneck.

The full audit timed out at 590 s. The water test is the suspect: the GSHHG L1
land polygon for continental Africa is a single ring with tens of thousands of
vertices, and point-in-ring over it is O(vertices) per test.

    python tool/profile_water_test.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import SEED, WaterIndex, canonical  # noqa: E402


def main() -> int:
    data = json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))
    t0 = time.time()
    idx = WaterIndex(data["elements"])
    print(f"index built in {time.time() - t0:.1f}s")
    print(f"  water rings: {len(idx.water)}  land rings: {len(idx.land)}")

    # Ring size distribution — the land rings are the worry.
    for label, rings in (("water", idx.water), ("land", idx.land)):
        sizes = sorted((len(r[1]) for r in rings), reverse=True)
        print(f"  {label} ring vertex counts (top 5): {sizes[:5]}")

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    pts = [(s["lat"], s["lon"]) for s in seed["stations"] if s.get("lat") and s.get("lon")]
    print(f"\ntesting {len(pts)} points...")

    t0 = time.time()
    hits = 0
    for i, (lat, lon) in enumerate(pts):
        if idx.contains(lat, lon):
            hits += 1
        if i and i % 1000 == 0:
            el = time.time() - t0
            print(f"  {i} points in {el:.1f}s ({el / i * 1000:.1f} ms/point, "
                  f"projected total {el / i * len(pts):.0f}s)")
    el = time.time() - t0
    print(f"\n{len(pts)} points in {el:.1f}s -> {el / len(pts) * 1000:.1f} ms/point, {hits} in water")
    return 0


if __name__ == "__main__":
    sys.exit(main())
