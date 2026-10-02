#!/usr/bin/env python3
"""Second-pass OSM audit in ONE Overpass call.

Earlier attempts split the country into 6 region queries and 824 per-cell
probes; the public Overpass instances rate-limited both (HTTP 504). A single
`out body` over the whole country is one request and is what the API is meant
for — the regional split was solving a problem I had created.

Includes generic `public_transport=*` so metro stops tagged only
`public_transport=stop` (no `highway`/`railway` key) are matched, which a
narrower tag list wrongly reported as missing.

Writes the fetched nodes to --cache so re-analysis costs nothing.

    python tool/audit_unmatched.py --seed <path> [--cache osm_nodes.json]
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]

TUNISIA = "32.4,7.0,37.7,11.9"  # S,W,N,E

QUERY = """
[out:json][timeout:600];
(
  node["public_transport"]({bbox});
  node["highway"="bus_stop"]({bbox});
  node["railway"="station"]({bbox});
  node["railway"="halt"]({bbox});
  node["railway"="tram_stop"]({bbox});
);
out body;
"""


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def fetch(bbox: str) -> list[dict]:
    data = urllib.parse.urlencode(
        {"data": QUERY.format(bbox=bbox)}
    ).encode()
    last = None
    for attempt, url in enumerate(ENDPOINTS):
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": "bledi-tn-audit/1.0"}
            )
            with urllib.request.urlopen(req, timeout=700) as r:
                return json.load(r)["elements"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  {url} -> {exc}", flush=True)
            if attempt + 1 < len(ENDPOINTS):
                time.sleep(15)
    raise SystemExit(f"all Overpass endpoints failed: {last}")


def label(tags: dict) -> str:
    for k in ("name:latin", "int_name", "name:fr", "name:en", "name"):
        v = (tags.get(k) or "").strip()
        if v:
            return v
    return "(unnamed)"


def classify(tags: dict) -> str:
    if tags.get("railway") in {"station", "halt", "tram_stop"}:
        return "rail"
    if tags.get("public_transport") in {"platform", "stop_position"}:
        return "rail" if (tags.get("railway") or tags.get("train") == "yes") else "bus"
    if tags.get("highway") == "bus_stop":
        return "bus"
    if tags.get("public_transport") == "station":
        return "rail"
    return "other"


def norm(s: str) -> str:
    """Loose name key: strip accents, case and punctuation for comparison."""
    import unicodedata

    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(s.split())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--cache", default="", help="write/read OSM nodes here")
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    cache = Path(args.cache) if args.cache else None
    if cache and cache.is_file():
        osm = json.loads(cache.read_text(encoding="utf-8"))
        print(f"loaded {len(osm)} OSM nodes from cache {cache}")
    else:
        print(f"querying Overpass for all of Tunisia ({TUNISIA}) — one request", flush=True)
        t0 = time.time()
        osm = fetch(TUNISIA)
        osm = [e for e in osm if e.get("type") == "node" and e.get("lat") and e.get("lon")]
        print(f"  {len(osm)} transport nodes in {time.time() - t0:.0f}s")
        if cache:
            cache.write_text(json.dumps(osm, ensure_ascii=False), encoding="utf-8")
            print(f"  cached to {cache}")

    seed = [
        s
        for s in json.loads(Path(args.seed).read_text(encoding="utf-8"))["stations"]
        if s.get("lat") and s.get("lon")
    ]
    print(f"seed stations: {len(seed)}")

    cell = max(args.tolerance / 111320.0, 1e-4)
    buckets: dict[tuple[int, int], list[dict]] = {}
    for e in osm:
        buckets.setdefault((int(e["lat"] // cell), int(e["lon"] // cell)), []).append(e)

    def near(lat, lon):
        out = []
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                out.extend(buckets.get((ky + dy, kx + dx), []))
        return out

    matched, missing, conflicts, name_bad = [], [], [], []
    for st in seed:
        best, best_d = None, None
        for cand in near(st["lat"], st["lon"]):
            d = haversine_m(st["lat"], st["lon"], cand["lat"], cand["lon"])
            if best_d is None or d < best_d:
                best, best_d = cand, d
        if best is None or best_d > args.tolerance:
            missing.append((st, best_d))
            continue

        tags = best.get("tags", {})
        kind = classify(tags)
        matched.append((st, best, best_d, kind))

        m = st.get("mode")
        if m in {"train", "metro", "rail"} and kind == "bus":
            conflicts.append((st, best, best_d, kind, "seed rail/metro vs OSM bus"))
        elif m == "bus" and kind == "rail":
            conflicts.append((st, best, best_d, kind, "seed bus vs OSM rail"))

        # Name agreement, accent/case/punctuation insensitive.
        ours = norm(st.get("name", ""))
        theirs = {norm(label(tags)), norm(tags.get("name", ""))}
        if ours and ours not in theirs:
            name_bad.append((st, best, best_d))

    print("\n=== second-pass audit (generic public_transport included) ===")
    print(f"  seed stations checked     : {len(seed)}")
    print(f"  matched within {args.tolerance:.0f} m      : {len(matched)} ({len(matched) / len(seed) * 100:.1f}%)")
    print(f"  still no OSM stop nearby  : {len(missing)}")
    print(f"  mode conflicts with OSM   : {len(conflicts)}")
    print(f"  name mismatch on match    : {len(name_bad)}")

    print(f"\n=== mode conflicts (first {args.limit}) ===")
    for st, e, d, kind, why in conflicts[: args.limit]:
        print(f"  {st['name'][:30]:30s} {why:26s} {d:.0f} m -> {label(e.get('tags', {}))[:26]}")

    print(f"\n=== name mismatches on confirmed pairs (first {args.limit}) ===")
    for st, e, d in name_bad[: args.limit]:
        print(f"  ours {st['name'][:28]:28s} vs OSM {label(e.get('tags', {}))[:30]:30s} ({d:.0f} m)")

    print(f"\n=== still missing (first {args.limit}) ===")
    for st, d in sorted(missing, key=lambda x: x[1] or 1e9)[: args.limit]:
        near_s = "no node within tolerance" if d is None else f"nearest {d:.0f} m"
        print(f"  {st['name'][:34]:34s} {st['lat']:.4f},{st['lon']:.4f}  {st.get('mode')}  {near_s}")


if __name__ == "__main__":
    main()