#!/usr/bin/env python3
"""Compare our seed against the official operator exports.

This is the authority check the OSM audit could not complete. OSM left 26
rail-vs-bus conflicts unresolved because those nodes carry no operator and no
`railway` tag — absence of OSM evidence, not evidence our label was wrong. The
operator exports (SNCFT, RFR, TRANSTU, TGM...) state what each stop actually is.

Reports, per mode:
  * how much of our rail/metro seed is corroborated by an operator export
  * how many official stops we have no station for
  * whether any of our labels are contradicted

Read-only. Writes nothing.

    python tool/compare_with_official.py --seed <path> --official stops.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
import unicodedata
from pathlib import Path

RAILISH = {"train", "metro", "rail"}
# Our seed's `metro` covers TGM light rail; `rail`/`train` cover SNCFT and RFR.
OFFICIAL_TO_OURS = {"train": {"train", "rail"}, "metro": {"metro"}, "bus": {"bus"}}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in s).split())


def haversine(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    x = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(x))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--official", required=True)
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    seed = [s for s in json.loads(Path(args.seed).read_text(encoding="utf-8"))["stations"]
            if s.get("lat") and s.get("lon")]
    official = json.loads(Path(args.official).read_text(encoding="utf-8"))

    print(f"our seed stations ............ {len(seed)}")
    print(f"official operator stops ..... {len(official)}")
    print(f"tolerance ................... {args.tolerance:.0f} m\n")

    print("=== official inventory ===")
    for op, n in collections.Counter(r["operator"] for r in official).most_common():
        modes = collections.Counter(r["mode"] for r in official if r["operator"] == op)
        print(f"  {op:10s} {n:5d}   {dict(modes)}")

    cell = max(args.tolerance / 111320.0, 1e-4)
    index: dict[tuple[int, int], list[dict]] = {}
    for r in official:
        index.setdefault((int(r["lat"] // cell), int(r["lon"] // cell)), []).append(r)

    def nearest(lat, lon):
        best, bd = None, None
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in index.get((ky + dy, kx + dx), []):
                    d = haversine(lat, lon, c["lat"], c["lon"])
                    if bd is None or d < bd:
                        best, bd = c, d
        return best, bd

    matched, absent, contradict, nameless = [], [], [], []
    for s in seed:
        r, dist = nearest(s["lat"], s["lon"])
        if r is None or dist > args.tolerance:
            absent.append((s, dist))
            continue
        matched.append((s, r, dist))
        ours = s.get("mode")
        theirs = r["mode"]
        # Only a contradiction if the operator says a different transport kind.
        if ours in OFFICIAL_TO_OURS.get(theirs, set()) or ours == theirs:
            continue
        if ours in RAILISH or theirs in RAILISH:
            contradict.append((s, r, dist, ours, theirs))
        if not r.get("name"):
            nameless.append((s, r, dist))

    used = {id(r) for _, r, _ in matched}
    official_only = [r for r in official if id(r) not in used]

    print("\n=== coverage ===")
    print(f"  our stations corroborated by an operator export : {len(matched)} "
          f"({len(matched) / len(seed) * 100:.1f}%)")
    print(f"  our stations with no official stop nearby       : {len(absent)}")
    print(f"  official stops we have no station for           : {len(official_only)}")

    # The question the OSM audit left open.
    print("\n=== rail/metro seed, checked against operator exports ===")
    rail_seed = [s for s in seed if s.get("mode") in RAILISH]
    rail_ok = [1 for s, r, d in matched
               if s.get("mode") in RAILISH and r["mode"] in {"train", "metro"}]
    rail_bus = [1 for s, r, d in matched
                if s.get("mode") in RAILISH and r["mode"] == "bus"]
    rail_none = [s for s in rail_seed
                 if not any(x[0]["id"] == s["id"] for x in matched)]
    print(f"  our rail/metro stations .................. {len(rail_seed)}")
    print(f"  corroborated as rail by an operator ..... {len(rail_ok)}")
    print(f"  operator says BUS instead ................ {len(rail_bus)}")
    print(f"  no official stop nearby .................. {len(rail_none)}")
    if rail_seed:
        print(f"  -> {len(rail_ok) / len(rail_seed) * 100:.1f}% of our rail/metro "
              f"labels are confirmed by the operator")

    print(f"\n=== contradictions (operator says a different mode) === {len(contradict)}")
    for s, r, dist, ours, theirs in contradict[: args.limit]:
        print(f"  {s['name'][:30]:30s} ours={ours:6s} official={theirs:6s} "
              f"({dist:5.0f} m, {r['operator']})")

    print(f"\n=== our stations absent from the official exports ({len(absent)}) ===")
    for s, dist in sorted(absent, key=lambda x: x[1] or 1e9)[: args.limit]:
        near_s = "no official stop nearby" if dist is None else f"nearest {dist:.0f} m"
        print(f"  {s['name'][:32]:32s} {str(s.get('mode')):6s} "
              f"{s['lat']:.4f},{s['lon']:.4f}  {near_s}")

    print(f"\n=== official stops we lack, by operator and mode ===")
    by: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in official_only:
        by[(r["operator"], r["mode"])].append(r)
    for (op, mode), rows in sorted(by.items(), key=lambda kv: -len(kv[1]))[:12]:
        print(f"  {op:10s} {mode:6s} {len(rows):5d}")
    print(f"\n  total official-only: {len(official_only)}")
    shown = 0
    for (op, mode), rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
        for r in rows:
            if shown >= args.limit:
                break
            print(f"    [{op}/{mode}] {r['name'][:30]:30s} {r['lat']:.4f},{r['lon']:.4f}")
            shown += 1

    print(f"\n=== naming ({len(nameless)} matched with an unnamed official stop) ===")
    if nameless:
        for s, r, dist in nameless[:8]:
            print(f"  ours {s['name'][:30]:30s} official stop unnamed ({dist:.0f} m, {r['operator']})")


if __name__ == "__main__":
    main()