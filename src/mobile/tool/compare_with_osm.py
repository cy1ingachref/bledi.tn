#!/usr/bin/env python3
"""Compare BLEDI.TN seed stops against live OpenStreetMap public-transport data.

The wiki URL referenced during this work
(`wiki.openstreetmap.org/wiki/Tunisia#/map/0/10/36.6640/10.0937`) is a map
*viewport*, not a dataset — the page carries no stop data. What that map draws
comes from OpenStreetMap, so OSM is the ground truth for "which stops exist,
and where".

One pass, area-scoped: comparing a whole-country seed against a single city's
viewport would report every out-of-area station as missing.

Reports seed stations with no OSM counterpart, OSM stops we lack, and name /
mode agreement on confirmed pairs. See docs/osm-stop-audit.md for the findings.

    python tool/compare_with_osm.py --bbox 36.60,10.00,36.75,10.20
    python tool/compare_with_osm.py          # whole country
"""

from __future__ import annotations

import argparse
from pathlib import Path

from osm_common import (
    TUNISIA_BBOX,
    bucket_index,
    cell_for,
    classify,
    in_bbox,
    label,
    load_osm_cache,
    load_seed,
    names_match,
    nearest,
    parse_bbox,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--seed",
        default=str(
            Path(__file__).resolve().parents[3] / "data" / "seed_all_tunisia_routes.tagged.json"
        ),
    )
    ap.add_argument("--cache", default=str(Path(__file__).with_name("osm_nodes_cache.json")))
    ap.add_argument("--bbox", default=TUNISIA_BBOX, help="S,W,N,E")
    ap.add_argument("--tolerance", type=float, default=250.0, help="metres")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    bb = parse_bbox(args.bbox)
    all_seed = load_seed(args.seed)
    seed = [s for s in all_seed if in_bbox(s["lat"], s["lon"], bb)]

    print(f"seed stations (whole country) : {len(all_seed)}")
    print(f"seed stations inside bbox    : {len(seed)}")
    print(f"bbox {args.bbox}  tolerance {args.tolerance:.0f} m")

    osm = load_osm_cache(args.cache)
    in_area = [e for e in osm if in_bbox(e["lat"], e["lon"], bb)]
    print(f"OSM transport nodes in area  : {len(in_area)}")

    cell = cell_for(args.tolerance)
    index = bucket_index(in_area, cell)

    matched, pairs, missing = 0, [], []
    for st in seed:
        node, dist = nearest((st["lat"], st["lon"]), index, cell)
        if node is None or dist > args.tolerance:
            missing.append((st, dist))
            continue
        matched += 1
        pairs.append((st, node, dist))

    used = {id(n) for _, n, _ in pairs}
    extra = [e for e in in_area if id(e) not in used]

    print("\n=== summary ===")
    print(f"  seed matched to OSM          : {matched} ({matched / max(len(seed), 1) * 100:.1f}%)")
    print(f"  seed with no OSM counterpart : {len(missing)}")
    print(f"  OSM stops we do not have     : {len(extra)}")
    print(f"  name mismatch on match       : {sum(1 for s, n, _ in pairs if not names_match(s['name'], n.get('tags', {})))}")

    print(f"\n=== our stations with no OSM counterpart (first {args.limit}) ===")
    for st, dist in sorted(missing, key=lambda x: x[1] or 1e9)[: args.limit]:
        near_s = "no OSM node nearby" if dist is None else f"nearest {dist:.0f} m"
        print(f"  {st['name'][:40]:40s} {st['lat']:.4f},{st['lon']:.4f}  {near_s}")

    print(f"\n=== OSM stops we do not have (first {args.limit}) ===")
    for e in sorted(extra, key=lambda x: (-x["lat"], x["lon"]))[: args.limit]:
        tags = e.get("tags", {})
        print(f"  {label(tags)[:40]:40s} {e['lat']:.4f},{e['lon']:.4f}  {classify(tags)}")


if __name__ == "__main__":
    main()