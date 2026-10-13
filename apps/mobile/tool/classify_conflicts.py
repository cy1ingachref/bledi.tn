#!/usr/bin/env python3
"""Classify seed stations whose OSM counterpart disagrees on mode.

The first pass compares positions. This one asks the sharper question: for the
stations our seed tags `train`/`metro`/`rail` whose nearest OSM node is a bus
stop, is our mode wrong, or is OSM merely coarse?

Answer, per station, from the seed's own line table: a station tagged `metro`
that its seed *also* serves from bus lines is a multi-modal interchange, so a
bus-tagged OSM node next to it is not evidence of an error. One that only rail
lines serve is a candidate.

Works entirely from the node cache, so it costs no Overpass calls.

    python tool/classify_conflicts.py --seed <path>
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

from osm_common import (
    bucket_index,
    cell_for,
    is_bus_stop,
    label,
    load_osm_cache,
    load_seed,
    names_match,
    nearest,
)

RAIL = {"train", "metro", "rail"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--cache", default=str(Path(__file__).with_name("osm_nodes_cache.json")))
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    import json

    raw = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    stations = [s for s in raw["stations"] if s.get("lat") and s.get("lon")]

    # Which lines serve each station, and of what mode.
    serving: dict[str, set[str]] = collections.defaultdict(set)
    for line in raw.get("lines", []):
        for sid in line.get("stations") or []:
            if isinstance(sid, str):
                serving[sid].add(line.get("mode"))

    osm = load_osm_cache(args.cache)
    cell = cell_for(args.tolerance)
    index = bucket_index(osm, cell)

    conflicts, name_bad, pairs = [], [], 0
    for st in stations:
        node, dist = nearest((st["lat"], st["lon"]), index, cell)
        if node is None or dist > args.tolerance:
            continue
        pairs += 1
        if not names_match(st["name"], node.get("tags", {})):
            name_bad.append((st, node, dist))
        if st.get("mode") in RAIL and is_bus_stop(node.get("tags", {})):
            conflicts.append((st, node, dist, serving.get(st["id"], set())))

    only_rail = [c for c in conflicts if c[3] and c[3] <= RAIL]
    also_bus = [c for c in conflicts if c[3] - RAIL]
    no_lines = [c for c in conflicts if not c[3]]

    print(f"confirmed pairs within {args.tolerance:.0f} m : {pairs}")
    print(f"name mismatches on those pairs           : {len(name_bad)}")
    print(f"\nmode conflicts (seed rail vs OSM bus)    : {len(conflicts)}")
    print(f"  our seed also serves them from bus     : {len(also_bus)}")
    print(f"  our seed serves them from rail only    : {len(only_rail)}")
    print(f"  no line references them at all        : {len(no_lines)}")

    print(f"\n=== multi-modal in our own seed (first {args.limit}) ===")
    for st, node, dist, modes in also_bus[: args.limit]:
        print(
            f"  {st['name'][:30]:30s} mode={st.get('mode'):6s} lines={sorted(modes)} "
            f"({dist:.0f} m, OSM: {label(node.get('tags', {}))[:22]})"
        )

    print(f"\n=== rail-only in our seed — the ones to double-check (first {args.limit}) ===")
    for st, node, dist, modes in only_rail[: args.limit]:
        tags = node.get("tags", {})
        print(
            f"  {st['name'][:30]:30s} mode={st.get('mode'):6s} lines={sorted(modes)} "
            f"({dist:.0f} m, OSM tags: {','.join(sorted(tags))[:34]})"
        )


if __name__ == "__main__":
    main()