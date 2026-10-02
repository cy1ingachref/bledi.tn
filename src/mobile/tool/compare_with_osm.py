#!/usr/bin/env python3
"""Compare BLEDI.TN seed stops against live OpenStreetMap public-transport data.

The wiki URL the user referenced is a map viewport, not a dataset. What that map
renders comes from OpenStreetMap, so OSM is the ground truth for "which stops
exist and where".

This queries Overpass for `public_transport=platform` (plus `highway=bus_stop`
and `railway=station`/`=halt`/`=tram_stop`, which many mappers tag instead),
then compares them with our seed **restricted to the same bbox** — comparing a
whole-country seed against one city's viewport would report every out-of-area
station as missing.

Reports:
  * seed stations in the area with no OSM counterpart within a tolerance
  * OSM stops in the area our seed has no station for
  * name and mode agreement on confirmed pairs

Read-only; writes nothing.

    python tool/compare_with_osm.py --bbox 36.60,10.00,36.75,10.20
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Stop-like OSM tags. `public_transport=platform` is the modern standard;
# the others are commonly used instead and would be missed without them.
QUERY = """
[out:json][timeout:{timeout}];
(
  node["public_transport"="platform"]({bbox});
  node["highway"="bus_stop"]({bbox});
  node["railway"="station"]({bbox});
  node["railway"="halt"]({bbox});
  node["railway"="tram_stop"]({bbox});
);
out body;
"""

TUNISIA_BBOX = "32.5,7.0,37.6,11.8"  # S,W,N,E


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def overpass(bbox: str, timeout: int = 180) -> list[dict]:
    q = QUERY.format(bbox=bbox, timeout=timeout)
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": "bledi-tn-audit/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout + 30) as r:
                return json.load(r)["elements"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  endpoint failed ({url}): {exc}", file=sys.stderr)
    raise SystemExit(f"all Overpass endpoints failed: {last}")


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    s, w, n, e = (float(x) for x in bbox.split(","))
    return s, w, n, e


def in_bbox(lat: float, lon: float, bb: tuple[float, ...]) -> bool:
    s, w, n, e = bb
    return s <= lat <= n and w <= lon <= e


def load_seed(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in data["stations"] if s.get("lat") and s.get("lon")]


def mode_of(tags: dict) -> str:
    if tags.get("railway") in {"station", "halt", "tram_stop"}:
        return "rail"
    return "bus"


def label_of(tags: dict) -> str:
    """Prefer a Latin name; Arabic-only names are hard to compare automatically."""
    for key in ("name:latin", "int_name", "name:fr", "name:en", "name"):
        val = (tags.get(key) or "").strip()
        if val:
            return val
    return "(unnamed)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seed",
        default=str(
            Path(__file__).resolve().parents[3]
            / "data" / "seed_all_tunisia_routes.tagged.json"
        ),
    )
    ap.add_argument("--bbox", default=TUNISIA_BBOX, help="S,W,N,E")
    ap.add_argument("--tolerance", type=float, default=200.0, help="metres")
    ap.add_argument("--limit-report", type=int, default=25)
    args = ap.parse_args()

    seed_path = Path(args.seed)
    if not seed_path.is_file():
        raise SystemExit(f"seed not found: {seed_path}")

    bb = parse_bbox(args.bbox)
    all_seed = load_seed(seed_path)
    seed = [s for s in all_seed if in_bbox(s["lat"], s["lon"], bb)]

    print(f"seed stations (whole country): {len(all_seed)}")
    print(f"seed stations inside bbox    : {len(seed)}")
    print(f"bbox {args.bbox}  tolerance {args.tolerance:.0f} m")

    print("\nquerying Overpass ...")
    t0 = time.time()
    elements = overpass(args.bbox)
    osm = [e for e in elements if e.get("type") == "node" and e.get("lat") and e.get("lon")]
    print(f"OSM stop nodes in bbox: {len(osm)}  ({time.time() - t0:.1f}s)")

    cell = max(args.tolerance / 111320.0, 1e-4)
    buckets: dict[tuple[int, int], list[dict]] = {}
    for e in osm:
        buckets.setdefault((int(e["lat"] // cell), int(e["lon"] // cell)), []).append(e)

    def near(lat: float, lon: float):
        out = []
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out.extend(buckets.get((ky + dy, kx + dx), []))
        return out

    matched, unmatched_seed, pairs = 0, [], []
    for s in seed:
        best, best_d = None, None
        for cand in near(s["lat"], s["lon"]):
            d = haversine_m(s["lat"], s["lon"], cand["lat"], cand["lon"])
            if best_d is None or d < best_d:
                best, best_d = cand, d
        if best is not None and best_d <= args.tolerance:
            matched += 1
            pairs.append((s, best, best_d))
        else:
            unmatched_seed.append((s, best_d))

    used = {id(b) for _, b, _ in pairs}
    unmatched_osm = [e for e in osm if id(e) not in used]

    print("\n=== summary ===")
    print(f"  seed stations in area        : {len(seed)}")
    print(f"  OSM stop nodes in area       : {len(osm)}")
    if seed:
        print(f"  seed matched to OSM          : {matched} ({matched / len(seed) * 100:.1f}%)")
    print(f"  seed in area NOT found in OSM: {len(unmatched_seed)}")
    print(f"  OSM stops in area missing    : {len(unmatched_osm)}")

    print(f"\n=== our stations with no OSM counterpart (first {args.limit_report}) ===")
    for s, d in sorted(unmatched_seed, key=lambda x: x[1] or 1e9)[: args.limit_report]:
        dist = "no OSM node nearby" if d is None else f"nearest {d:.0f} m"
        print(f"  {s['name'][:40]:40s} {s['lat']:.4f},{s['lon']:.4f}  {dist}")

    print(f"\n=== OSM stops we do not have (first {args.limit_report}) ===")
    for e in sorted(unmatched_osm, key=lambda x: (-x["lat"], x["lon"]))[: args.limit_report]:
        tags = e.get("tags", {})
        print(f"  {label_of(tags)[:40]:40s} {e['lat']:.4f},{e['lon']:.4f}  {mode_of(tags)}")

    print("\n=== agreement on matched pairs ===")
    print(f"  matched pairs : {len(pairs)}")
    name_miss = [
        (s, e) for s, e, _ in pairs
        if (s.get("name") or "").strip().lower()
        not in label_of(e.get("tags", {})).strip().lower()
    ]
    print(f"  our name not in OSM labels   : {len(name_miss)}")
    for s, e in name_miss[:10]:
        print(f"      ours {s['name'][:34]:34s} vs OSM {label_of(e.get('tags', {}))[:34]}")

    seed_rail = sum(1 for s in seed if s.get("mode") in {"train", "metro", "rail"})
    matched_rail = sum(1 for s, e, _ in pairs if mode_of(e.get("tags", {})) == "rail")
    print(f"  rail stations (seed, in area) : {seed_rail}")
    print(f"    matched to rail OSM nodes    : {matched_rail}")


if __name__ == "__main__":
    main()