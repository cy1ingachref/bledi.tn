#!/usr/bin/env python3
"""Debug the rasterised water mask: is anything actually being drawn?

    python tool/debug_water_mask.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import WaterIndex  # noqa: E402


def main() -> int:
    data = json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))
    els = data["elements"]
    print(f"elements in file: {len(els)}")

    kinds: dict[str, int] = {}
    for el in els:
        t = el.get("tags") or {}
        k = t.get("natural", "?")
        kinds[k] = kinds.get(k, 0) + 1
    print("kinds:", kinds)

    # Check a land element's ring size and coordinate range.
    land = [e for e in els if (e.get("tags") or {}).get("natural") == "land"]
    print(f"\nland elements: {len(land)}")
    if land:
        g = land[0]["geometry"]
        lats = [p["lat"] for p in g]
        lons = [p["lon"] for p in g]
        print(f"  first land ring: {len(g)} pts, lat {min(lats):.3f}..{max(lats):.3f}, "
              f"lon {min(lons):.3f}..{max(lons):.3f}")
        # How many land elements overlap the window at all?
        inwin = 0
        for e in land:
            gg = e["geometry"]
            la = [p["lat"] for p in gg]
            lo = [p["lon"] for p in gg]
            if not (max(la) < 30.0 or min(la) > 37.8 or max(lo) < 7.0 or min(lo) > 12.0):
                inwin += 1
        print(f"  land elements overlapping the window: {inwin}")

    idx = WaterIndex(els)
    print(f"\nmasks: water={idx.water_mask.shape} sum={idx.water_mask.sum()}, "
          f"land={idx.land_mask.shape} sum={idx.land_mask.sum()}")
    print(f"water rings drawn: {idx.n_water_rings}, land rings drawn: {idx.n_land_rings}")

    # Where is the mask set, if anywhere?
    if idx.land_mask.sum():
        rows, cols = np.where(idx.land_mask)
        print(f"  land mask covers rows {rows.min()}..{rows.max()}, cols {cols.min()}..{cols.max()}")
        lats = idx.north - rows * idx.RES
        lons = cols * idx.RES + idx.west
        print(f"  -> lat {lats.min():.2f}..{lats.max():.2f}, lon {lons.min():.2f}..{lons.max():.2f}")
    if idx.water_mask.sum():
        rows, cols = np.where(idx.water_mask)
        lats = idx.north - rows * idx.RES
        lons = cols * idx.RES + idx.west
        print(f"  water mask -> lat {lats.min():.2f}..{lats.max():.2f}, "
              f"lon {lons.min():.2f}..{lons.max():.2f}")

    # Sample the test points directly.
    for lat, lon, desc in [
        (36.8065, 10.1815, "Tunis"),
        (37.10, 10.60, "Gulf of Tunis"),
        (33.70, 8.40, "Chott el Djerid"),
    ]:
        rc = idx._idx(lat, lon)
        if rc is None:
            print(f"  {desc}: OUT OF MASK RANGE")
            continue
        r, c = rc
        print(f"  {desc}: idx={rc} water={bool(idx.water_mask[r, c])} "
              f"land={bool(idx.land_mask[r, c])} -> {idx.contains(lat, lon)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
