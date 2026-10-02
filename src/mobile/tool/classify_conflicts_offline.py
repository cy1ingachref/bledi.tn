#!/usr/bin/env python3
"""Classify the seed/OSM mode conflicts using cached data only.

Live Overpass queries for each conflict get rate-limited (HTTP 504) after a
handful of calls, so this works from the node cache already fetched by
`audit_unmatched.py --cache`. For every conflict it reports the *tags* of the
nearest OSM stop, which is what actually distinguishes "OSM maps this halt as a
bus stop" from "our mode is simply wrong".

It also answers the question the audit exists to answer: for each conflicting
station, does the seed itself also serve it from bus lines? A station tagged
`train` that is simultaneously a bus stop is a genuine mis-tag in our seed; one
that is purely rail is OSM being coarse.

    python tool/classify_conflicts_offline.py --seed <path> --cache <nodes.json>
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import unicodedata
from pathlib import Path


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in s).split())


def label(tags: dict) -> str:
    for k in ("name:latin", "int_name", "name:fr", "name:en", "name"):
        v = (tags.get(k) or "").strip()
        if v:
            return v
    return "(unnamed)"


def is_bus(tags: dict) -> bool:
    if tags.get("railway") in {"station", "halt", "tram_stop"}:
        return False
    return tags.get("highway") == "bus_stop" or tags.get("public_transport") in {
        "platform",
        "stop_position",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    data = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    stations = [s for s in data["stations"] if s.get("lat") and s.get("lon")]
    lines = data.get("lines", [])

    # Which lines serve each station, and what modes are those lines?
    lines_by_station: dict[str, list[dict]] = collections.defaultdict(list)
    for ln in lines:
        for sid in ln.get("stations") or []:
            if isinstance(sid, str):
                lines_by_station[sid].append(ln)

    osm = json.loads(Path(args.cache).read_text(encoding="utf-8"))
    cell = args.tolerance / 111320.0
    buckets: dict[tuple[int, int], list[dict]] = {}
    for e in osm:
        buckets.setdefault((int(e["lat"] // cell), int(e["lon"] // cell)), []).append(e)

    conflicts = []
    for st in stations:
        if st.get("mode") not in {"train", "metro", "rail"}:
            continue
        best, best_d = None, None
        ky, kx = int(st["lat"] // cell), int(st["lon"] // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in buckets.get((ky + dy, kx + dx), []):
                    d = haversine_m(st["lat"], st["lon"], c["lat"], c["lon"])
                    if best_d is None or d < best_d:
                        best, best_d = c, d
        if best is not None and best_d <= args.tolerance and is_bus(best.get("tags", {})):
            conflicts.append((st, best, best_d))

    print(f"mode conflicts: {len(conflicts)}\n")

    # For each, what modes does OUR seed say serve it?
    pure_rail, also_bus, no_lines = [], [], []
    for st, node, d in conflicts:
        modes = {ln.get("mode") for ln in lines_by_station.get(st["id"], [])}
        if not modes:
            no_lines.append((st, node, d, modes))
        elif modes - {"train", "metro", "rail"}:
            also_bus.append((st, node, d, modes))
        else:
            pure_rail.append((st, node, d, modes))

    print("=== what our own seed says serves each conflicting station ===")
    print(f"  served ONLY by rail lines in our seed : {len(pure_rail)}")
    print(f"  ALSO served by bus lines in our seed  : {len(also_bus)}")
    print(f"  no lines reference the station at all : {len(no_lines)}")

    print(f"\n=== stations our seed serves from BOTH rail and bus (first {args.limit}) ===")
    for st, node, d, modes in also_bus[: args.limit]:
        print(
            f"  {st['name'][:32]:32s} seed mode={st.get('mode'):6s} lines={sorted(modes)} "
            f"({d:.0f} m, OSM: {label(node.get('tags', {}))[:22]})"
        )

    print(f"\n=== served only by rail in our seed (first {args.limit}) ===")
    for st, node, d, modes in pure_rail[: args.limit]:
        print(
            f"  {st['name'][:32]:32s} mode={st.get('mode'):6s} lines={sorted(modes)} "
            f"({d:.0f} m, OSM tags it: {','.join(sorted(node.get('tags', {})))[:40]})"
        )

    # The OSM tag vocabulary actually seen on the conflicting nodes.
    print("\n=== tag vocabulary on conflicting OSM nodes ===")
    vocab = collections.Counter()
    for _, node, _ in conflicts:
        tags = node.get("tags", {})
        for key in ("public_transport", "highway", "railway", "bus"):
            if key in tags:
                vocab[f"{key}={tags[key]}"] += 1
    for k, v in vocab.most_common():
        print(f"  {k:28s} {v}")

    # Name quality: how many OSM-confirmed pairs differ only by accents/spacing?
    pairs = []
    for st in stations:
        best, best_d = None, None
        ky, kx = int(st["lat"] // cell), int(st["lon"] // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in buckets.get((ky + dy, kx + dx), []):
                    d = haversine_m(st["lat"], st["lon"], c["lat"], c["lon"])
                    if best_d is None or d < best_d:
                        best, best_d = c, d
        if best is not None and best_d <= args.tolerance:
            pairs.append((st, best, best_d))
    same, diff = 0, []
    for st, node, d in pairs:
        ours = norm(st.get("name", ""))
        theirs = {norm(label(node.get("tags", {}))), norm(node.get("tags", {}).get("name", ""))}
        if ours and ours in theirs:
            same += 1
        else:
            diff.append((st, node, d))
    print(f"\n=== names on {len(pairs)} confirmed pairs ===")
    print(f"  exact (accent/case-insensitive): {same}")
    print(f"  differing                     : {len(diff)}")
    print("  sample of differing names (our spelling may be the abbreviated one):")
    for st, node, d in diff[:12]:
        print(f"    ours {st['name'][:26]:26s} | OSM {label(node.get('tags', {}))[:34]:34s} ({d:.0f} m)")


if __name__ == "__main__":
    main()