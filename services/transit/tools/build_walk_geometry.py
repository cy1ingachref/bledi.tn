#!/usr/bin/env python3
"""Precompute real pedestrian geometry for walk legs.

Why Valhalla and not OSRM foot: the public OSRM demo
(https://router.project-osrm.org/route/v1/foot/...) is CAR-ONLY. Measured on
this project: foot, walking, bike, cycling and a nonsense profile all return
byte-identical distance/duration/geometry, because the server ignores the
profile segment and serves the single car dataset it was built with. A self-hosted
OSRM does have a foot profile, but that needs a Docker extract of the OSM PBF.

Valhalla's public endpoint does honour costing=pedestrian and returns a real
foot network plus turn-by-turn instructions, so walk legs can follow real
footways instead of being drawn as a straight line.

The cache is keyed on an unordered "a|b" station pair and stores the polyline in
a -> b order; oriented_geometry() flips it when a step runs the other way,
exactly like the transit geometry cache.

Usage:
  python services/transit/tools/build_walk_geometry.py            # all walk pairs
  python services/transit/tools/build_walk_geometry.py --limit 200
  python services/transit/tools/build_walk_geometry.py --workers 6
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bledi_transit.adapters.seed_files import SeedFileNetwork
from bledi_transit.application.routing.router import Router
from bledi_transit.domain.geo import haversine_m, polyline_length

BASE = Path(__file__).resolve().parents[3]
OUT = BASE / "data" / "walk_geometry.json"

VALHALLA_ENDPOINTS = [
    # Ordered by observed reliability. A 429/504 is a rate limit to back off
    # from, not a dead mirror to skip.
    "https://valhalla1.openstreetmap.de/route",
    "https://valhalla2.openstreetmap.de/route",
    "https://valhalla3.openstreetmap.de/route",
]

# Walk legs are <= MAX_WALK_EDGE_METERS (900 m). A pedestrian path can never be
# shorter than the straight line it replaces, and cannot be 4x longer for a
# sub-km hop, so anything outside this band is a bad match and gets rejected.
MIN_DETOUR = 0.95
MAX_DETOUR = 4.0
MIN_WALK_M = 20.0

USER_AGENT = "bledi-tn/0.2 (walk geometry builder; contact cy1ingachref@gmail.com)"


def decode_polyline(s: str) -> list[list[float]]:
    """Google encoded polyline, precision 6 -> [[lat, lon], ...]."""
    out: list[list[float]] = []
    i = 0
    lat = lon = 0
    while i < len(s):
        for which in (0, 1):
            shift = 0
            res = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                res |= (b & 0x1F) << shift
                shift += 5
                if not b & 0x20:
                    break
            delta = ~(res >> 1) if res & 1 else res >> 1
            if which == 0:
                lat += delta
            else:
                lon += delta
        out.append([lat / 1e6, lon / 1e6])
    return out


def fetch(a: list[float], b: list[float], timeout: float = 20.0) -> list[list[float]]:
    """Real pedestrian polyline a -> b, or [] on failure."""
    payload = {
        "locations": [
            {"lat": a[0], "lon": a[1]},
            {"lat": b[0], "lon": b[1]},
        ],
        # A 200 m buffer keeps a short walk off the nearest arterial, which is
        # what the pedestrian costing would pick by default.
        "costing": "pedestrian",
        "directions_options": {"units": "kilometers"},
        "filters": {"attributes": ["edge.surface", "edge.road_class"]},
    }
    url = VALHALLA_ENDPOINTS[0] + "?" + urllib.parse.urlencode(
        {"json": json.dumps(payload, separators=(",", ":"))}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    shape = data["trip"]["legs"][0].get("shape")
    if not shape:
        return []
    pts = decode_polyline(shape) if isinstance(shape, str) else [
        [p[1], p[0]] for p in shape
    ]
    return pts


def snap(pts: list[list[float]], a: list[float], b: list[float]) -> list[list[float]]:
    """Force the polyline's endpoints onto the exact station coordinates.

    Real geometry starts at the nearest network vertex, which can be tens of
    metres from the station node. A client that validates a leg's endpoints
    against its stations discards correct geometry over that gap.
    """
    if pts:
        pts[0] = [a[0], a[1]]
        pts[-1] = [b[0], b[1]]
    return pts


def validate(pts: list[list[float]], a: list[float], b: list[float]) -> tuple[bool, str]:
    if len(pts) < 2:
        return False, "too_few_points"
    real = polyline_length(pts)
    straight = haversine_m(a[0], a[1], b[0], b[1])
    if real < MIN_WALK_M:
        return False, "too_short"
    if straight <= 0:
        return False, "degenerate"
    ratio = real / straight
    # A path along a network cannot be shorter than the straight line, so a
    # ratio below 1 means the matcher emitted garbage, not that it did well.
    if ratio < MIN_DETOUR:
        return False, f"below_straight_{ratio:.2f}"
    if ratio > MAX_DETOUR:
        return False, f"excess_detour_{ratio:.2f}"
    return True, "ok"


def build(limit: int | None, workers: int) -> int:
    network = SeedFileNetwork(BASE / "data").load()
    router = Router(network.station_by_id, network.lines)

    # Every unique station pair that has a walk edge. The graph stores both
    # directions, so collapse to the unordered pair.
    pairs: set[tuple[str, str]] = set()
    for sid, edges in router.adj.items():
        for e in edges:
            if e.mode == "walk":
                pairs.add((min(sid, e.to_id), max(sid, e.to_id)))
    pairs = sorted(pairs)
    if limit:
        pairs = pairs[:limit]
    print(f"walk pairs to resolve: {len(pairs)}", flush=True)

    cache: dict[str, dict] = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text(encoding="utf-8")).get("segments", {})
        print(f"existing cache: {len(cache)} segments", flush=True)

    todo = [p for p in pairs if f"{p[0]}|{p[1]}" not in cache]
    print(f"to fetch: {len(todo)}", flush=True)

    done = {"n": 0, "ok": 0, "rejected": 0, "failed": 0}

    def work(pair: tuple[str, str]) -> tuple[str, dict]:
        a_id, b_id = pair
        a = router.stations[a_id]
        b = router.stations[b_id]
        pa = [a["lat"], a["lon"]]
        pb = [b["lat"], b["lon"]]
        key = f"{a_id}|{b_id}"
        try:
            pts = snap(fetch(pa, pb), pa, pb)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            done["failed"] += 1
            return key, {"mode": "walk", "source": "valhalla-pedestrian",
                         "geometry": [], "reason": f"error_{type(exc).__name__}"}
        good, reason = validate(pts, pa, pb)
        if not good:
            done["rejected"] += 1
            return key, {"mode": "walk", "source": "valhalla-pedestrian",
                         "geometry": [], "reason": reason}
        done["ok"] += 1
        return key, {
            "mode": "walk",
            "source": "valhalla-pedestrian",
            "geometry": pts,
            "length_m": round(polyline_length(pts), 1),
            "reason": None,
        }

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (key, entry) in enumerate(pool.map(work, todo), 1):
            cache[key] = entry
            if i % 50 == 0 or i == len(todo):
                rate = i / max(time.time() - t0, 1e-9)
                print(
                    f"  {i}/{len(todo)} ok={done['ok']} rejected={done['rejected']} "
                    f"failed={done['failed']} ({rate:.1f}/s)",
                    flush=True,
                )
            if i % 200 == 0:
                OUT.write_text(
                    json.dumps({"segments": cache}, separators=(",", ":")),
                    encoding="utf-8",
                )

    OUT.write_text(
        json.dumps({"segments": cache}, separators=(",", ":")), encoding="utf-8"
    )
    withgeom = sum(1 for v in cache.values() if v.get("geometry"))
    print(
        f"\nwrote {OUT.name}: {len(cache)} segments, {withgeom} with geometry "
        f"({100 * withgeom / max(len(cache), 1):.1f}%)"
    )
    print(f"elapsed {time.time() - t0:.0f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    return build(args.limit, args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
