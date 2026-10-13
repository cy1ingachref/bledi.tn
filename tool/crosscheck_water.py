#!/usr/bin/env python3
"""Cross-check the raster water mask against an exact polygon test.

The raster mask is fast but can be wrong for two reasons: the ~150 m cell is
coarser than a shoreline, and PIL's fill can bleed. This re-tests every flagged
station with exact ray casting against the same polygons, so a raster artefact
can be told apart from a genuine "this coordinate is in a water polygon".

    python tool/crosscheck_water.py --report out/audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import WaterIndex, point_in_ring  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", default="out/audit.json")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    rep = json.loads((ROOT / args.report).read_text(encoding="utf-8"))
    flagged = rep.get("in_water", [])
    print(f"flagged in water: {len(flagged)}\n")

    data = json.loads((ROOT / "data" / "water_polys.json").read_text(encoding="utf-8"))
    idx = WaterIndex(data["elements"])

    # Exact rings, split by class.
    water_rings: list[tuple[str, list]] = []
    land_rings: list[tuple[str, list]] = []
    for el in data["elements"]:
        tags = el.get("tags") or {}
        kind = tags.get("natural") or "water"
        geom = el.get("geometry") or []
        if len(geom) < 3:
            continue
        ring = [(p["lon"], p["lat"]) for p in geom]
        (land_rings if kind == "land" else water_rings).append((kind, ring))

    print(f"exact rings available: water={len(water_rings)} land={len(land_rings)}\n")

    def exact(lat: float, lon: float) -> tuple[str | None, str | None]:
        """Return (water_kind, land_kind) by exact ray casting."""
        wk = lk = None
        for kind, ring in water_rings:
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if not (min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons)):
                continue
            if point_in_ring(lon, lat, ring):
                wk = kind
                break
        for kind, ring in land_rings:
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if not (min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons)):
                continue
            if point_in_ring(lon, lat, ring):
                lk = kind
                break
        return wk, lk

    agree = raster_only = 0
    print(f"{'station':30s} {'raster':13s} {'exact water':14s} {'exact land':10s} verdict")
    for f in flagged[: args.limit]:
        lat, lon = f["lat"], f["lon"]
        wk, lk = exact(lat, lon)
        exact_water = wk is not None and lk is None
        if exact_water:
            agree += 1
            verdict = "confirmed"
        else:
            raster_only += 1
            verdict = "RASTER ARTEFACT"
        print(f"{str(f['name'])[:30]:30s} {str(f.get('water'))[:13]:13s} "
              f"{str(wk)[:14]:14s} {str(lk)[:10]:10s} {verdict}")

    print(f"\nconfirmed by exact test: {agree}")
    print(f"raster-only (artefact):  {raster_only}")
    if raster_only:
        print("\nRaster artefacts mean the cell size is too coarse; the mask must be "
              "rebuilt finer or the flagged set re-tested exactly before reporting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
