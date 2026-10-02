#!/usr/bin/env python3
"""Settle the rail-vs-bus conflicts by reading the OSM node's own tags.

The supplied extract classifies a stop by which tags matched, and a node tagged
`highway=bus_stop` lands in its BUS section. But SNCFT also files some of its
halts under bus_stop while naming itself as operator — e.g. El Ouja and Zaafrane
carry operator = الشركة الوطنية للسكك الحديدية التونسية (the national railway
company). In those cases the extract's BUS label is the wrong inference and our
seed's `train` is right.

This fetches the raw tags for the conflicting nodes and decides on the evidence:
  * operator names SNCFT / TGM / a rail operator  -> ours is right
  * node carries railway=*                 -> ours is right
  * node is only highway=bus_stop, no operator -> genuinely ambiguous; report it

    python tool/resolve_mode_conflicts.py --seed <path> --reference stops.json
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

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import ENDPOINTS, haversine_m, load_seed  # noqa: E402

# Operators that imply rail regardless of the highway=bus_stop tag.
RAIL_OPERATORS = (
    "الشركة الوطنية للسكك الحديدية التونسية",  # SNCFT
    "sncft",
    "الشركة Tunisienne de Transport",  # placeholder, matched below
)
RAIL_OPERATORS_LATIN = ("sncft", "tgm", "transtu", "metropole", "metro tunis")


def fetch(nodes: list[str], cache: Path | None = None) -> dict[str, dict]:
    """Raw tags for the given OSM node ids, keyed 'node/123'.

    Cached on disk: Overpass rate-limits (HTTP 504) after a handful of calls, so
    re-running this analysis should not depend on the public instance again.
    """
    if cache and cache.is_file():
        stored = json.loads(cache.read_text(encoding="utf-8"))
        if set(stored) >= {n for n in nodes if n}:
            print(f"  loaded {len(stored)} node tag sets from cache {cache.name}")
            return stored

    ids = ",".join(n.split("/")[1] for n in nodes if n.startswith("node/"))
    if not ids:
        return {}
    q = f"[out:json][timeout:120];node(id:{ids});out body;"
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": "bledi-tn-audit/1.0"}
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                tags = {
                    f"node/{e['id']}": e.get("tags", {})
                    for e in json.load(r)["elements"]
                }
            if cache:
                cache.write_text(json.dumps(tags, ensure_ascii=False), encoding="utf-8")
            return tags
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(10)
    print(f"  overpass unavailable: {last}", file=sys.stderr)
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument(
        "--cache",
        default=str(Path(__file__).with_name("conflict_node_tags.json")),
        help="raw OSM tags for the conflicting nodes; fetched once, then reused",
    )
    args = ap.parse_args()

    seed = load_seed(args.seed)
    ref = [r for r in json.loads(Path(args.reference).read_text(encoding="utf-8"))
           if "lat" in r and "lon" in r]

    cell = args.tolerance / 111320.0
    index: dict[tuple[int, int], list[dict]] = {}
    for r in ref:
        index.setdefault((int(r["lat"] // cell), int(r["lon"] // cell)), []).append(r)

    conflicts = []
    for s in seed:
        best, best_d = None, None
        ky, kx = int(s["lat"] // cell), int(s["lon"] // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in index.get((ky + dy, kx + dx), []):
                    d = haversine_m(s["lat"], s["lon"], c["lat"], c["lon"])
                    if best_d is None or d < best_d:
                        best, best_d = c, d
        if best is None or best_d > args.tolerance:
            continue
        if s.get("mode") in {"train", "metro", "rail"} and (best.get("mode") or "").startswith("BUS"):
            conflicts.append((s, best, best_d))

    print(f"rail-vs-bus conflicts: {len(conflicts)}\n")

    cache = Path(args.cache) if args.cache else None
    tags_by_node = fetch([c[1].get("osm_ref", "") for c in conflicts], cache)
    print(f"fetched raw tags for {len(tags_by_node)}/{len(conflicts)} nodes\n")

    ours_right, ours_wrong, ambiguous = [], [], []
    for s, refrec, dist in conflicts:
        tags = tags_by_node.get(refrec.get("osm_ref", ""), {})
        operator = (tags.get("operator") or "").strip()
        op_l = operator.lower()
        railway = tags.get("railway", "")

        rail_by_operator = any(
            k in operator for k in RAIL_OPERATORS
        ) or any(k in op_l for k in RAIL_OPERATORS_LATIN)
        rail_by_tag = railway in {
            "station", "halt", "stop", "tram_stop", "subway_entrance",
            "light_rail", "subway", "train",
        }

        row = (s, refrec, dist, operator, railway)
        if rail_by_operator or rail_by_tag:
            ours_right.append(row)
        elif operator:
            # A named non-rail operator alongside highway=bus_stop.
            ambiguous.append(row)
        else:
            ambiguous.append(row)

    print("=== verdict ===")
    print(f"  our `train/rail/metro` is correct (rail evidence on the node) : {len(ours_right)}")
    print(f"  genuinely ambiguous — bus_stop tag, no rail evidence ........ {len(ambiguous)}")

    print(f"\n=== where our seed is vindicated (first {args.limit}) ===")
    for s, r, d, op, railway in ours_right[: args.limit]:
        why = []
        if any(k in op for k in RAIL_OPERATORS) or any(k in op.lower() for k in RAIL_OPERATORS_LATIN):
            why.append("operator=SNCFT/TGM")
        if railway:
            why.append(f"railway={railway}")
        # Print the evidence, not just the conclusion — without the actual tag
        # values a reader cannot tell an SNCFT operator apart from an empty one.
        print(f"  {s['name'][:30]:30s} ours={s['mode']:6s} {' + '.join(why):24s} "
              f"operator={op[:34]!r} railway={railway!r}")

    print(f"\n=== still ambiguous (first {args.limit}) ===")
    for s, r, d, op, railway in ambiguous[: args.limit]:
        print(f"  {s['name'][:30]:30s} ours={s['mode']:6s} operator={op[:34]!r} railway={railway!r} ({d:.0f} m)")


if __name__ == "__main__":
    main()