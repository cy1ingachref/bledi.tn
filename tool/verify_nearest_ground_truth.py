#!/usr/bin/env python3
"""Brute-force ground truth for the audit's "no neighbour" and "no track" claims.

The audit uses a grid index with a bounded search radius, so a "none" result
could be either a real finding (nothing nearby) or a search artefact (the
neighbour exists outside the search window). This script recomputes the
nearest neighbour over ALL stops for the specific ids the audit flagged, so
the two cases can be told apart. O(n) per id over 7 465 stops, so only the
flagged ids are checked.

    python tool/verify_nearest_ground_truth.py --report out/audit.json
"""

from __future__ import annotations

import argparse
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
    LOUAGE,
    canonical,
    haversine_m,
)


def load_all() -> list[dict]:
    rows: list[dict] = []
    data = json.loads(SEED.read_text(encoding="utf-8"))
    for s in data["stations"]:
        if s.get("lat") and s.get("lon"):
            rows.append({
                "id": s.get("id"), "name": (s.get("name") or "").strip(),
                "lat": s["lat"], "lon": s["lon"], "mode": canonical(s.get("mode")),
            })
    if LOUAGE.is_file():
        d = json.loads(LOUAGE.read_text(encoding="utf-8"))
        for s in d.get("stations", []):
            loc = s.get("location") or {}
            if loc.get("lat") and loc.get("lon"):
                rows.append({
                    "id": f"louage_{s.get('id')}",
                    "name": (s.get("name_fr") or s.get("id") or "").strip(),
                    "lat": loc["lat"], "lon": loc["lon"], "mode": "louaj",
                })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", required=True, help="audit JSON with 'isolated'/'rail_mismatch'")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    rep = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = load_all()
    by_id = {r["id"]: r for r in rows}
    print(f"loaded {len(rows)} placed stops for brute-force comparison\n")

    # 1. Isolated claims: recompute the true nearest stop over ALL stops.
    isolated = [x for x in rep.get("isolated", []) if x.get("nearest_stop_m") is None]
    print(f"=== verifying {len(isolated)} 'no neighbour' claims (brute force over all stops) ===")
    artifacts = 0
    for x in isolated[: args.limit]:
        me = by_id.get(x["id"])
        if me is None:
            print(f"  ? {x['id']} not in loaded set")
            continue
        best, dist = None, math.inf
        for r in rows:
            if r["id"] == me["id"]:
                continue
            d = haversine_m(me["lat"], me["lon"], r["lat"], r["lon"])
            if d < dist:
                best, dist = r, d
        km = dist / 1000.0
        verdict = "ARTEFACT" if km < 13.0 else "confirmed"
        if verdict == "ARTEFACT":
            artifacts += 1
        print(f"  [{verdict:9s}] {me['name'][:26]:26s} true nearest: "
              f"{str(best['name'])[:26]:26s} {str(best['mode']):6s} {km:7.1f} km")
    if artifacts:
        print(f"\n  !! {artifacts} of {min(len(isolated), args.limit)} were SEARCH ARTEFACTS")
    else:
        print(f"\n  all checked 'no neighbour' claims confirmed at >13 km")

    # 2. Rail claims: how much rail geometry exists at all?
    print("\n=== rail geometry coverage (limits the rail placement test) ===")
    segs = json.loads(GEOMETRY.read_text(encoding="utf-8")).get("segments", {})
    per_mode: dict[str, dict[str, int]] = {}
    for seg in segs.values():
        m = canonical(seg.get("mode"))
        if m not in RAIL_LIKE:
            continue
        e = per_mode.setdefault(m, {"with_geom": 0, "no_geom": 0, "pts": 0})
        pts = seg.get("geometry") or []
        if len(pts) >= 2:
            e["with_geom"] += 1
            e["pts"] += len(pts)
        else:
            e["no_geom"] += 1
    rail_stops: dict[str, int] = {}
    for r in rows:
        if r["mode"] in RAIL_LIKE:
            rail_stops[r["mode"]] = rail_stops.get(r["mode"], 0) + 1
    for m in sorted(RAIL_LIKE):
        e = per_mode.get(m, {})
        print(f"  {m:6s} stops={rail_stops.get(m, 0):4d}  "
              f"segments with track={e.get('with_geom', 0):4d}  "
              f"without={e.get('no_geom', 0):3d}  vertices={e.get('pts', 0)}")

    # 3. What fraction of train stops sit near any rail vertex, at a generous
    #    radius? Tells us whether "far from track" is data error or missing track.
    rail_pts: list[tuple[float, float]] = []
    for seg in segs.values():
        if canonical(seg.get("mode")) in RAIL_LIKE:
            for lat, lon in seg.get("geometry") or []:
                rail_pts.append((lat, lon))
    print(f"\n  total rail/track vertices available: {len(rail_pts)}")
    if rail_pts:
        # 0.01 deg cells, check up to ~30 km by scanning a coarse bucket set.
        cell = 0.05
        buckets: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for la, lo in rail_pts:
            buckets.setdefault((int(la // cell), int(lo // cell)), []).append((la, lo))

        def near_track_km(lat: float, lon: float, rings: int = 6) -> float:
            ky, kx = int(lat // cell), int(lon // cell)
            best = math.inf
            for dy in range(-rings, rings + 1):
                for dx in range(-rings, rings + 1):
                    for la, lo in buckets.get((ky + dy, kx + dx), ()):
                        d = haversine_m(lat, lon, la, lo)
                        if d < best:
                            best = d
            return best / 1000.0

        far = []
        for r in rows:
            if r["mode"] != "train":
                continue
            km = near_track_km(r["lat"], r["lon"])
            if km == math.inf or km > 5.0:
                far.append((r, km))
        print(f"  train stops >5 km from any rail vertex (or none within 30 km): {len(far)}")
        for r, km in far[: args.limit]:
            shown = "none<30km" if km == math.inf else f"{km:6.1f} km"
            print(f"    {r['name'][:30]:30s} {r['lat']:9.5f},{r['lon']:9.5f} {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
