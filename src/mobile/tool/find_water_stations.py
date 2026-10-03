#!/usr/bin/env python3
"""Find stations that sit in water, and stations that sit nowhere evidenced.

Reports, never mutates. Two lists come out, and the separation matters:

  inside water   the point falls inside an OSM water polygon or coastline.
                 This is the only finding.

  near water     the point falls within N km of a lake's approximate centre.
                 NOT a finding. Tunis has a lake inside the city, so its own
                 districts satisfy this; conflating the two produced 29 false
                 positives on the first run.

  isolated       no official operator stop within --isolation metres. This is
                 the signal that catches a coordinate typed for the wrong town:
                 such a point is often on dry land, so proximity to nothing
                 real is the only evidence available.

Water polygons come from Overpass and are cached to disk, because Overpass
rate-limits and this must be re-runnable offline.

    python tool/find_water_stations.py --seed <seed> --official <stops.json>
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import haversine_m  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"

# Lakes, lagoons and reservoirs in Tunisia, as (name, lat, lon, radius_km).
# These centres and radii are approximate and exist only to *shortlist* stops
# for a human to look at. Nothing here decides a station is on water; only an
# OSM polygon does.
KNOWN_WATER = [
    ("Lac de Tunis", 36.83, 10.25, 3.2),
    ("El Kaluet", 36.90, 10.21, 1.6),
    ("Lac Manzour", 35.72, 10.22, 3.0),
    ("Lac Sidi El Halk", 36.93, 10.35, 1.4),
    ("Lac de Ichkeul", 37.13, 8.86, 3.0),
    ("Barrage de Sidi Salem", 36.42, 9.53, 2.4),
    ("Barrage de Sidi M'amel", 35.62, 10.10, 1.2),
    ("Lac de Beja", 36.73, 9.18, 1.5),
    ("Lac de Tabarka", 36.95, 8.75, 1.2),
    ("Chott Melah", 35.25, 10.35, 3.0),
    ("Chott el Djerid", 33.80, 8.30, 10.0),
    ("Chott Ghiglet", 33.93, 8.30, 3.0),
    ("Sebkha el Hiri", 34.25, 8.30, 2.5),
    ("Lac de Sidi Ali Ben Hamdouch", 34.30, 9.30, 1.0),
    ("Lac de Yf", 36.55, 8.95, 1.0),
]


def load_water(cache: Path, bbox: tuple[float, float, float, float]) -> list[dict]:
    """Fetch coastline/lake polygons for the bbox, cached to disk."""
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))

    south, west, north, east = bbox
    q = (
        '[out:json][timeout:180];'
        '(way["natural"~"water|coastline|bay"](%s,%s,%s,%s);'
        'relation["natural"="water"](%s,%s,%s,%s););out geom;'
        % (south, west, north, east, south, west, north, east)
    )
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS, data=data)
    with urllib.request.urlopen(req, timeout=300) as r:
        payload = json.loads(r.read().decode("utf-8"))
    cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload["elements"]


def point_in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xint = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < xint:
                inside = not inside
    return inside


def on_water(lon: float, lat: float, elements: list[dict]) -> tuple[bool, str]:
    for el in elements:
        tags = el.get("tags") or {}
        kind = "coastline" if tags.get("natural") == "coastline" else "water"
        label = tags.get("name") or tags.get("natural") or kind
        if el["type"] == "way":
            geom = el.get("geometry")
            if not geom:
                continue
            if point_in_ring(lon, lat, [(p["lon"], p["lat"]) for p in geom]):
                return True, f"{kind}: {label}"
        else:
            # A multipolygon relation is a list of rings; a point in the hole of
            # an inner ring is still in the relation, which is what we want for
            # a lake.
            for member in el.get("members", []):
                mg = member.get("geometry")
                if mg and point_in_ring(lon, lat, [(p["lon"], p["lat"]) for p in mg]):
                    return True, f"{kind}: {label}"
    return False, ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--official", default="")
    ap.add_argument("--water", default="water_polys.json")
    ap.add_argument("--bbox", default="30.2,7.3,37.6,11.7")
    ap.add_argument("--isolation", type=float, default=400.0,
                    help="metres; a station with no neighbour and no official "
                         "stop this close is suspicious")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    data = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    stations = [s for s in data["stations"] if s.get("lat") and s.get("lon")]
    print(f"stations in seed: {len(stations)}")

    # Official operator stops: an authoritative position for most of the network.
    official = []
    if args.official and Path(args.official).is_file():
        official = [r for r in json.loads(
            Path(args.official).read_text(encoding="utf-8"))
            if r.get("lat") and r.get("lon")]
        print(f"official places for comparison: {len(official)}")

    bbox = tuple(float(x) for x in args.bbox.split(","))
    try:
        water = load_water(Path(args.water), bbox)
        print(f"OSM water polygons: {len(water)}")
    except Exception as exc:  # noqa: BLE001
        print(f"water fetch failed ({exc}); falling back to known lakes only")
        water = []

    # Spatial index over the official places.
    cell = 0.02
    off_grid: dict[tuple[int, int], list[dict]] = collections.defaultdict(list)
    for r in official:
        off_grid[(int(r["lat"] // cell), int(r["lon"] // cell))].append(r)

    def nearest_official(lat: float, lon: float):
        best, dist = None, math.inf
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in off_grid.get((ky + dy, kx + dx), []):
                    d = haversine_m(lat, lon, c["lat"], c["lon"])
                    if d < dist:
                        best, dist = c, d
        return best, dist

    hits: list[tuple[dict, str]] = []
    near_water: list[tuple[dict, str]] = []
    isolated: list[tuple[dict, float]] = []
    for s in stations:
        lat, lon = s["lat"], s["lon"]
        ok, why = on_water(lon, lat, water) if water else (False, "")
        if ok:
            hits.append((s, f"inside {why}"))
            continue
        for name, wlat, wlon, radius in KNOWN_WATER:
            if haversine_m(lat, lon, wlat, wlon) < radius * 1000:
                # Not a finding. Tunis has a lake inside the city, so its own
                # districts fall inside these radii; reporting them as "on
                # water" was the false positive this separation exists to stop.
                near_water.append((s, f"within {radius} km of {name}"))
                break
        if official:
            _, d = nearest_official(lat, lon)
            if d > args.isolation:
                isolated.append((s, d))

    print(f"\n=== stations inside a water polygon: {len(hits)}")
    for s, why in sorted(hits, key=lambda h: h[0]["name"]):
        print(f"  {s['name'][:34]:34s} {s['lat']:8.5f},{s['lon']:8.5f}  "
              f"{s.get('mode',''):7s} {why}")

    print(f"\n=== merely near a lake, NOT reported as on water: {len(near_water)}")
    print("    (Tunis sits on a lake; proximity proves nothing)")

    print(f"\n=== isolated stations (no official stop within "
          f"{args.isolation:.0f} m): {len(isolated)}")
    for s, d in sorted(isolated, key=lambda h: -h[1])[:40]:
        print(f"  {s['name'][:34]:34s} {s['lat']:8.5f},{s['lon']:8.5f}  "
              f"{s.get('mode',''):7s} {s.get('city','')[:14]:14s} {d:7.0f} m")

    by_mode = collections.Counter(s.get("mode") for s, _ in hits)
    print(f"\non-water breakdown: {dict(by_mode)}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"on_water": [{"id": s["id"], "name": s["name"], "lat": s["lat"],
                           "lon": s["lon"], "mode": s.get("mode"),
                           "reason": why} for s, why in hits],
             "near_water_not_flagged": [{"name": s["name"], "lat": s["lat"],
                                         "lon": s["lon"], "reason": why}
                                        for s, why in near_water],
             "isolated": [{"id": s["id"], "name": s["name"], "lat": s["lat"],
                           "lon": s["lon"], "mode": s.get("mode"),
                           "city": s.get("city"), "distance_m": round(d, 1)}
                          for s, d in isolated]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()