#!/usr/bin/env python3
"""Separate "station is misplaced" from "we have no track geometry for its line".

The audit flags rail/metro stops more than 5 km from any rail vertex. That
finding has two very different causes, and conflating them would be the mistake:

  a) the station's coordinate is wrong, or
  b) the line's track geometry was never cached, so there is nothing near it.

(b) is by far the more likely, because route_geometry.json only carries track
for a subset of lines. This script joins each flagged station to the lines that
serve it, then reports whether those lines have geometry at all.

    python tool/diagnose_rail_placement.py
"""

from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import (  # noqa: E402
    GEOMETRY,
    RAIL_LIKE,
    SEED,
    canonical,
    haversine_m,
)


def main() -> int:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    stations = {s.get("id"): s for s in data["stations"]}
    lines = data["lines"]

    segs = json.loads(GEOMETRY.read_text(encoding="utf-8")).get("segments", {})

    # Which consecutive stop pairs have cached geometry, and for which line?
    # route_geometry keys are "<stop_a>|<stop_b>".
    geom_pairs = {k for k, v in segs.items() if len(v.get("geometry") or []) >= 2}

    rail_lines = [ln for ln in lines if canonical(ln.get("mode")) in RAIL_LIKE]
    print(f"rail/metro/tram lines: {len(rail_lines)}")

    # Per line: how many of its consecutive stop pairs have geometry?
    line_cov: dict[str, dict] = {}
    for ln in rail_lines:
        stops = [s for s in (ln.get("stations") or []) if isinstance(s, str)]
        pairs = list(zip(stops, stops[1:]))
        have = sum(1 for a, b in pairs if f"{a}|{b}" in geom_pairs or f"{b}|{a}" in geom_pairs)
        line_cov[ln.get("id")] = {
            "name": ln.get("name"),
            "number": ln.get("number"),
            "mode": canonical(ln.get("mode")),
            "stops": len(stops),
            "pairs": len(pairs),
            "pairs_with_geom": have,
            "coverage": (have / len(pairs) * 100) if pairs else 0.0,
        }

    # Rail vertices for the proximity test.
    rail_pts: list[tuple[float, float]] = []
    for v in segs.values():
        if canonical(v.get("mode")) in RAIL_LIKE:
            rail_pts.extend((la, lo) for la, lo in (v.get("geometry") or []))
    cell = 0.05
    buckets: dict[tuple[int, int], list] = collections.defaultdict(list)
    for la, lo in rail_pts:
        buckets[(int(la // cell), int(lo // cell))].append((la, lo))

    def near_km(lat: float, lon: float, rings: int = 8) -> float:
        ky, kx = int(lat // cell), int(lon // cell)
        best = math.inf
        for dy in range(-rings, rings + 1):
            for dx in range(-rings, rings + 1):
                for la, lo in buckets.get((ky + dy, kx + dx), ()):
                    d = haversine_m(lat, lon, la, lo)
                    if d < best:
                        best = d
        return best / 1000.0

    # Stations served by rail-like lines.
    rail_stop_ids = set()
    stop_to_rail_lines: dict[str, list[str]] = collections.defaultdict(list)
    for ln in rail_lines:
        for s in (ln.get("stations") or []):
            if isinstance(s, str):
                rail_stop_ids.add(s)
                stop_to_rail_lines[s].append(ln.get("id"))

    flagged = []
    for sid in sorted(rail_stop_ids):
        st = stations.get(sid)
        if not st or not st.get("lat") or not st.get("lon"):
            continue
        km = near_km(st["lat"], st["lon"])
        if km == math.inf or km > 5.0:
            lids = stop_to_rail_lines[sid]
            covs = [line_cov[l] for l in lids if l in line_cov]
            covered = any(c["coverage"] > 0 for c in covs)
            flagged.append({
                "id": sid, "name": st.get("name"), "lat": st["lat"], "lon": st["lon"],
                "km": None if km == math.inf else round(km, 1),
                "lines": lids,
                "line_coverage": [
                    {"n": c["number"], "cov": round(c["coverage"]), "pairs": c["pairs"]}
                    for c in covs
                ],
                "any_line_has_geometry": covered,
            })

    print(f"rail stops >5 km from any rail vertex: {len(flagged)}\n")
    no_geom = [f for f in flagged if not f["any_line_has_geometry"]]
    has_geom = [f for f in flagged if f["any_line_has_geometry"]]
    print(f"  of those, served ONLY by lines with NO cached track: {len(no_geom)}"
          f"   <- data gap, not a misplaced point")
    print(f"  served by a line that DOES have some track:          {len(has_geom)}"
          f"   <- needs a look at the coordinate\n")

    if no_geom:
        print("  -- lines with zero cached geometry (their stops cannot be checked) --")
        zero = [c for c in line_cov.values() if c["pairs"] and c["pairs_with_geom"] == 0]
        for c in sorted(zero, key=lambda x: -x["pairs"])[:20]:
            print(f"    {str(c['number'])[:10]:10s} {str(c['name'])[:44]:44s} "
                  f"{c['mode']:6s} {c['pairs']} pairs, 0 traced")

    if has_geom:
        print("\n  -- stops whose line has SOME track: check these coordinates --")
        for f in sorted(has_geom, key=lambda x: -(x["km"] or 999))[:20]:
            lines_s = ", ".join(f"{c['n']}({c['cov']}%)" for c in f["line_coverage"][:3])
            print(f"    {str(f['name'])[:26]:26s} {f['lat']:9.5f},{f['lon']:9.5f} "
                  f"{str(f['km']):>7} km  {lines_s}")

    # Overall coverage summary for rail lines.
    tot_pairs = sum(c["pairs"] for c in line_cov.values())
    tot_have = sum(c["pairs_with_geom"] for c in line_cov.values())
    print(f"\n  rail geometry coverage overall: {tot_have}/{tot_pairs} stop pairs traced "
          f"({(tot_have / tot_pairs * 100) if tot_pairs else 0:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
