#!/usr/bin/env python3
"""Compare our seed against the supplied Tunisia transit stop extract.

The extract (`tunisia_transit_stops.txt`, OSM via Overpass, ODbL 1.0) is a
better reference than the ad-hoc Overpass query in compare_with_osm.py: it
queries 16 tag conventions rather than 3, de-duplicates stops that OSM maps
twice, and separates modes we have no seed data for (ferry, tram, light rail).

Answers three questions:
  1. coverage   — do our stations exist in the reference?
  2. modes      — where both know the stop, do the modes agree?
  3. gaps       — what does the reference know that we have no station for?

Read-only. Writes nothing.

    python tool/compare_with_reference.py --reference stops.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import haversine_m, norm  # noqa: E402

# The extract's mode vocabulary -> ours. LIGHT_RAIL_TGM is TGM, which our seed
# calls `metro`; UNKNOWN stays unknown rather than being guessed at.
MODE_MAP = {
    "BUS": "bus",
    "TRAIN": "train",
    "METRO": "metro",
    "LIGHT_RAIL_TGM": "metro",
    "FERRY": "ferry",
    "UNKNOWN": "unknown",
}

# Modes we can compare meaningfully. The extract's `?` variants are text-hint
# guesses its own caveats call out as unverified, so they are excluded from the
# agreement count but still reported.
CONFIRMED = {"BUS", "TRAIN", "METRO", "LIGHT_RAIL_TGM", "FERRY", "UNKNOWN"}


def load_reference(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def base_mode(mode: str) -> str:
    return mode.split()[0] if mode else "?"


def is_confirmed(mode: str) -> bool:
    return base_mode(mode) in CONFIRMED and not mode.rstrip().endswith("?")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--tolerance", type=float, default=250.0)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    seed_raw = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    seed = [s for s in seed_raw["stations"] if s.get("lat") and s.get("lon")]
    ref = load_reference(Path(args.reference))
    ref = [r for r in ref if "lat" in r and "lon" in r]

    print(f"our seed stations ............ {len(seed)}")
    print(f"reference stops .............. {len(ref)}")
    print(f"tolerance .................... {args.tolerance:.0f} m\n")

    ref_modes = collections.Counter(base_mode(r.get("mode", "?")) for r in ref)
    seed_modes = collections.Counter(s.get("mode") for s in seed)
    print("=== mode inventory (neither side is a subset of the other) ===")
    print(f"  {'mode':16s} {'ours':>6s} {'reference':>10s}")
    for m in sorted(set(ref_modes) | set(seed_modes)):
        print(f"  {m:16s} {seed_modes.get(m, 0):>6d} {ref_modes.get(m, 0):>10d}")

    # Spatial index over the reference.
    cell = max(args.tolerance / 111320.0, 1e-4)
    index: dict[tuple[int, int], list[dict]] = {}
    for r in ref:
        index.setdefault((int(r["lat"] // cell), int(r["lon"] // cell)), []).append(r)

    def nearest(lat: float, lon: float):
        best, best_d = None, None
        ky, kx = int(lat // cell), int(lon // cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in index.get((ky + dy, kx + dx), []):
                    d = haversine_m(lat, lon, c["lat"], c["lon"])
                    if best_d is None or d < best_d:
                        best, best_d = c, d
        return best, best_d

    matched, seed_absent, mode_conflict, name_bad = [], [], [], []
    for s in seed:
        r, dist = nearest(s["lat"], s["lon"])
        if r is None or dist > args.tolerance:
            seed_absent.append((s, dist))
            continue
        matched.append((s, r, dist))
        ours = s.get("mode")
        theirs = MODE_MAP.get(base_mode(r.get("mode", "")), "unknown")
        if ours != theirs and is_confirmed(r.get("mode", "")):
            mode_conflict.append((s, r, dist, ours, theirs))
        # Name agreement, using whichever latin name the reference carries.
        ref_names = {norm(r.get("name_fr", "")), norm(r.get("name_en", "")), norm(r.get("name", ""))}
        if norm(s.get("name", "")) not in ref_names:
            name_bad.append((s, r, dist))

    used = {id(r) for _, r, _ in matched}
    ref_missing = [r for r in ref if id(r) not in used]

    print("\n=== coverage ===")
    print(f"  our stations found in reference : {len(matched)} ({len(matched) / len(seed) * 100:.1f}%)")
    print(f"  our stations not in reference   : {len(seed_absent)}")
    print(f"  reference stops we have no station for : {len(ref_missing)}")

    print("\n=== agreement on confirmed pairs ===")
    print(f"  pairs compared .................. {len(matched)}")
    print(f"  mode conflicts .................. {len(mode_conflict)}")
    print(f"  name differs .................... {len(name_bad)}")

    # Only counts where both sides are confident.
    verified = [c for c in matched if is_confirmed(c[1].get("mode", ""))]
    vconf = [c for c in mode_conflict]
    if verified:
        print(f"  mode agreement where both certain : {len(verified) - len(vconf)}/{len(verified)} "
              f"({(len(verified) - len(vconf)) / len(verified) * 100:.1f}%)")

    # The reference's unconfirmed modes, called out rather than mixed in.
    unconf = [r for r in ref if not is_confirmed(r.get("mode", ""))]
    if unconf:
        print(f"\n  reference stops with a text-hint mode (excluded from agreement): {len(unconf)}")

    if mode_conflict:
        print(f"\n=== mode conflicts (first {args.limit}) ===")
        for s, r, dist, ours, theirs in mode_conflict[: args.limit]:
            print(f"  {s['name'][:30]:30s} ours={ours:7s} ref={theirs:7s} "
                  f"{dist:5.0f} m  ref='{r.get('name', '')[:24]}'")

    if seed_absent:
        print(f"\n=== our stations absent from the reference (first {args.limit}) ===")
        for s, dist in sorted(seed_absent, key=lambda x: x[1] or 1e9)[: args.limit]:
            near_s = "no ref stop nearby" if dist is None else f"nearest {dist:.0f} m"
            print(f"  {s['name'][:34]:34s} {s.get('mode'):7s} {s['lat']:.4f},{s['lon']:.4f}  {near_s}")

    if ref_missing:
        print(f"\n=== reference stops we lack, by mode (first {args.limit}) ===")
        by_mode: dict[str, list[dict]] = collections.defaultdict(list)
        for r in ref_missing:
            by_mode[base_mode(r.get("mode", "?"))].append(r)
        for m in sorted(by_mode, key=lambda k: -len(by_mode[k])):
            print(f"  {m}: {len(by_mode[m])}")
        shown = 0
        for m in sorted(by_mode, key=lambda k: -len(by_mode[k])):
            for r in by_mode[m]:
                if shown >= args.limit:
                    break
                label = r.get("name_fr") or r.get("name") or "(unnamed)"
                print(f"    [{m:6s}] {label[:32]:32s} {r['lat']:.4f},{r['lon']:.4f}")
                shown += 1

    print("\n=== name differences (first {n}) ===".format(n=min(args.limit, len(name_bad))))
    for s, r, dist in name_bad[: args.limit]:
        ref_label = r.get("name_fr") or r.get("name_en") or r.get("name") or "(unnamed)"
        print(f"  ours {s['name'][:26]:26s} | ref {ref_label[:32]:32s} ({dist:.0f} m)")


if __name__ == "__main__":
    main()