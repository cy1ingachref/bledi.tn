#!/usr/bin/env python3
"""Precompute road geometry for the direct Louaj / Taxi option.

A taxi leg is the one movement in the system that does NOT connect two
stations: it runs from the rider's origin to their destination. That means there
is no station pair to key the geometry cache on, and it also means the
station-pair cache built by build_route_geometry.py cannot serve it.

This fills that gap. The key is the coordinate pair at 5 decimal places
(~1.1 m), which is finer than any GPS fix the client sends, so a lookup either
hits the exact pair that was cached or misses cleanly rather than snapping to a
neighbouring trip.

Two sources, in priority order:

1. The local OSM roads GeoPackage (BLEDI_ROADS_GPKG, default
   ~/Downloads/roads/roads.gpkg) -- offline, deterministic, and no rate limit.
2. OSRM `driving` -- used only for pairs the local network cannot snap.

Both follow real roads. Nothing here is a straight line.

Usage:
  python src/backend/tool/build_taxi_geometry.py --pairs pairs.json
  python src/backend/tool/build_taxi_geometry.py --from-options
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
OUT = BASE / "data" / "taxi_geometry.json"
ROADS_GPKG = os.environ.get(
    "BLEDI_ROADS_GPKG", str(Path.home() / "Downloads" / "roads" / "roads.gpkg")
)
OSRM = "https://router.project-osrm.org/route/v1/driving"

# Same reasoning as the transit cache: a road path cannot be shorter than the
# straight line, and a car does not usefully triple the crow-flies distance
# except in a genuinely constrained city centre.
MIN_DETOUR = 0.95
MAX_DETOUR = 4.0
MIN_M = 20.0

# Coordinate quantisation for the cache key. 5dp ~ 1.1 m.
KEY_DP = 5

USER_AGENT = "bledi-tn/0.2 (taxi geometry builder; contact cy1ingachref@gmail.com)"


def haversine(p: list[float], q: list[float]) -> float:
    la1, lo1 = p[0], p[1]
    la2, lo2 = q[0], q[1]
    r = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(
        math.radians(lo2 - lo1) / 2
    ) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def polyline_length(pts: list[list[float]]) -> float:
    return sum(haversine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def key_for(a: list[float], b: list[float]) -> str:
    """Direction-independent key, matching the other caches: min first."""
    ka = (round(a[0], KEY_DP), round(a[1], KEY_DP))
    kb = (round(b[0], KEY_DP), round(b[1], KEY_DP))
    return (
        f"{ka[0]},{ka[1]}|{kb[0]},{kb[1]}"
        if ka <= kb
        else f"{kb[0]},{kb[1]}|{ka[0]},{ka[1]}"
    )


def snap(pts: list[list[float]], a: list[float], b: list[float]) -> list[list[float]]:
    """Force the endpoints onto the exact requested coordinates."""
    if pts:
        pts[0] = [a[0], a[1]]
        pts[-1] = [b[0], b[1]]
    return pts


def validate(pts: list[list[float]], a: list[float], b: list[float]) -> tuple[bool, str]:
    if len(pts) < 2:
        return False, "too_few_points"
    real = polyline_length(pts)
    straight = haversine(a, b)
    if real < MIN_M:
        return False, "too_short"
    if straight <= 0:
        return False, "degenerate"
    ratio = real / straight
    if ratio < MIN_DETOUR:
        return False, f"below_straight_{ratio:.2f}"
    if ratio > MAX_DETOUR:
        return False, f"excess_detour_{ratio:.2f}"
    return True, "ok"


def osrm_route(a: list[float], b: list[float], timeout: float = 25.0):
    """Real driving geometry from OSRM, or [] on failure."""
    url = (
        f"{OSRM}/{a[1]},{a[0]};{b[1]},{b[0]}"
        "?overview=full&geometries=geojson"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    coords = data["routes"][0]["geometry"]["coordinates"]
    # geojson is [lon, lat]; the project stores [lat, lon] everywhere.
    return [[c[1], c[0]] for c in coords]


# The roads GeoPackage is ~232 MB and takes seconds to decode, so it is loaded
# and gridded once per process rather than once per pair.
_NET: dict[str, object] = {}


def local_road_route(a: list[float], b: list[float]):
    """Slice of the local OSM road network between the two points.

    Uses the same matcher the transit geometry build uses, so a taxi leg and a
    bus leg between the same two points follow the same road.
    """
    if "grid" not in _NET:
        sys.path.insert(0, str(Path(__file__).parent))
        import build_route_geometry as B  # noqa: E402

        # Decoding the 232 MB GeoPackage takes over ten minutes on this machine.
        # BLEDI_SKIP_ROADS=1 falls through to OSRM, which needs no local file.
        skip = os.environ.get("BLEDI_SKIP_ROADS", "").strip() not in ("", "0", "false")
        lines = [] if skip else B.load_road_network()
        if skip:
            print("  BLEDI_SKIP_ROADS set: taxi legs will use OSRM driving")
        if lines:
            _NET["B"] = B
            _NET["lines"] = lines
            _NET["grid"] = B.build_grid(lines, 0.02)
        else:
            _NET["grid"] = None
    grid = _NET.get("grid")
    if not grid:
        return []
    B = _NET["B"]
    seg = B.path_on_network(
        _NET["lines"], grid, 0.02, (a[0], a[1]), (b[0], b[1])
    )
    return [[lat, lon] for lat, lon in seg] if seg else []


def build(pairs: list[tuple[list[float], list[float]]]) -> int:
    cache: dict[str, dict] = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text(encoding="utf-8")).get("segments", {})
        print(f"existing cache: {len(cache)} segments")

    stats = {"local": 0, "osrm": 0, "rejected": 0, "failed": 0}
    t0 = time.time()
    for i, (a, b) in enumerate(pairs, 1):
        key = key_for(a, b)
        if key in cache and cache[key].get("geometry"):
            continue
        pts: list[list[float]] = []
        src = None
        try:
            pts = local_road_route(a, b)
            if len(pts) >= 2:
                src = "osm-local-roads"
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  local failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if len(pts) < 2:
            try:
                pts = osrm_route(a, b)
                if len(pts) >= 2:
                    src = "osrm-driving"
            except Exception as exc:
                print(f"  osrm failed: {type(exc).__name__}", file=sys.stderr)
                cache[key] = {
                    "mode": "taxi",
                    "source": None,
                    "geometry": [],
                    "reason": f"error_{type(exc).__name__}",
                }
                stats["failed"] += 1
                continue
        # The cache stores min -> max on the key, like the transit cache, so
        # the polyline is REVERSED (not re-snapped) when the request runs the
        # other way. Re-snapping to the key's endpoints would leave the middle
        # of the path pointing the wrong way and double the measured length:
        # observed 267 km -> 738 km on Tunis->Sfax.
        ka, kb = key_for(a, b).split("|")
        pa_key = [float(x) for x in ka.split(",")]
        pb_key = [float(x) for x in kb.split(",")]
        if [round(a[0], KEY_DP), round(a[1], KEY_DP)] != [round(pa_key[0], KEY_DP),
                                                          round(pa_key[1], KEY_DP)]:
            pts = list(reversed(pts))
        pts = snap(pts, pa_key, pb_key)
        good, reason = validate(pts, pa_key, pb_key)
        if not good:
            stats["rejected"] += 1
            cache[key] = {"mode": "taxi", "source": src, "geometry": [],
                          "reason": reason}
            continue
        stats[src] = stats.get(src, 0) + 1
        cache[key] = {
            "mode": "taxi",
            "source": src,
            "geometry": pts,
            "length_m": round(polyline_length(pts), 1),
            "reason": None,
        }
        if i % 10 == 0:
            print(f"  {i}/{len(pairs)} {stats} ({time.time() - t0:.0f}s)", flush=True)

    OUT.write_text(json.dumps({"segments": cache}, separators=(",", ":")),
                   encoding="utf-8")
    withgeom = sum(1 for v in cache.values() if v.get("geometry"))
    print(f"\nwrote {OUT.name}: {len(cache)} segments, {withgeom} with geometry")
    print(f"stats: {stats}  elapsed {time.time() - t0:.0f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pairs", help="JSON file: [[lat,lon],[lat,lon]] pairs")
    ap.add_argument(
        "--from-options",
        action="store_true",
        help="read pairs from stdin as one [[lat,lon],[lat,lon]] per line",
    )
    args = ap.parse_args()
    if not args.pairs and not args.from_options:
        ap.error("need --pairs or --from-options")
    if args.pairs:
        raw = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    else:
        raw = [json.loads(ln) for ln in sys.stdin if ln.strip()]
    pairs = [(p[0], p[1]) for p in raw]
    print(f"pairs: {len(pairs)}  roads.gpkg present: {Path(ROADS_GPKG).exists()}")
    return build(pairs)


if __name__ == "__main__":
    raise SystemExit(main())
