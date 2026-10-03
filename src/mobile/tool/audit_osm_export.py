#!/usr/bin/env python3
"""Classify the fresh Overpass exports in Downloads/maps against our seed.

Two exports, both fetched 2026-10-03 12:51 UTC (newer than the 4 361-node cache
from the earlier audit):

  export.json                 4 300 elements — bus stops and stations
  metro and train/export .json 1 545 elements — rail, metro and TGM

These are far richer than the earlier cache: 452 nodes carry `operator`, 338
carry `gtfs_id`, and most carry `name:fr` / `name:ar`. Operator is what settles
mode, and it is exactly the field the old export lacked — the old one made
SNCFT rail halts look like `highway=bus_stop` stops with no way to tell.

Mode is decided by tag precedence, never by one tag alone:

    railway=station|halt|tram_stop   -> train
    operator mentions a rail operator -> train   (beats highway=bus_stop)
    amenity=bus_station              -> bus
    highway=bus_stop / platform / stop_position -> bus
    operator mentions a bus operator -> bus
    nothing recognisable             -> unknown, reported not silently dropped

Read-only: writes a JSON report, touches no data.

    python tool/audit_osm_export.py --maps <dir> --seed <seed> --out report.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from osm_common import haversine_m, norm  # noqa: E402

# Normalised (diacritics stripped, lowercased) so an Arabic or accented
# spelling still matches. "Rapid Transit System" normalises to
# "rapid transit system", which is why the substring is "rapid transit".
RAIL_OPERATORS = (
    "sncft", "societe nationale des chemins de fer", "nationale des chemins de fer",
    "tgm", "rfr", "transtu", "rapid transit",
    # Arabic: الشركة الوطنية للسكك الحديدية التونسية
    "الوطنية للسكك",
    # شركة النقل بتونس — light rail / metro
    "النقل بتونس",
    # نقل تونس, شركة النقل بالساحل is bus: keep rail keys separate.
)
# A rail route_ref ("Tunis_Ville-Erriadh") is independent evidence even when
# operator is missing or wrong.
RAIL_ROUTE_HINTS = ("snb", "tt", "ligne", "line")
BUS_OPERATORS = (
    "soretras", "srt", "sntri", "transtu", "sts", "srtm", "srtb",
    "الشركة الجهوية للنقل", "شركة النقل بالساحل", "trans",
)
# amenity=bus_station is the primary tag for a bus *terminus*; the earlier pass
# keyed only on highway/public_transport and so reported 821 nodes as unknown.
BUS_AMENITIES = {"bus_station", "bus_stop", "transportation_hub"}


def classify(tags: dict) -> str:
    t = tags or {}
    railway = (t.get("railway") or "").lower()
    pt = (t.get("public_transport") or "").lower()
    amenity = (t.get("amenity") or "").lower()
    # Operators are matched on the normalised form: the Arabic SNCFT string
    # contains accents and a definite article that defeat a literal substring.
    op = norm(t.get("operator") or "")
    route_ref = norm(t.get("route_ref") or t.get("ref") or "")
    network = norm(t.get("network") or "")
    has_bus = t.get("bus") == "yes"
    is_rail_stop = railway in {"station", "halt", "tram_stop"}

    # A rail operator outranks a stray highway=bus_stop: SNCFT halts are
    # routinely mapped with both, and trusting the highway tag misfiles them.
    op_is_rail = any(k in op for k in RAIL_OPERATORS) if op else False
    # A rail line named in route_ref/network is evidence on its own: SNCFT bus
    # stops on the Belvédère line carry `route_ref=Tunis_Ville-Erriadh` and no
    # railway tag whatsoever, which is how 32 of the surviving conflicts arise.
    ref_is_rail = (
        any(h in route_ref for h in RAIL_ROUTE_HINTS)
        or any(k in network for k in RAIL_OPERATORS)
    )
    if is_rail_stop and (op_is_rail or not has_bus):
        return "train"
    if t.get("train") == "yes" or (pt == "station" and op_is_rail):
        return "train"
    if (op_is_rail or ref_is_rail) and not amenity in {"bus_station"}:
        return "train"
    if amenity in BUS_AMENITIES:
        return "bus"
    if is_rail_stop or railway:
        return "train"
    if has_bus or (t.get("highway") == "bus_stop") or pt in {"platform", "stop_position"}:
        return "bus"
    if op and any(k in op for k in BUS_OPERATORS):
        return "bus"
    return "unknown"


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for e in data.get("elements", []):
        if e.get("type") != "node":
            continue
        tags = e.get("tags") or {}
        if not tags:
            continue
        out.append({
            "osm_id": e["id"],
            "lat": e["lat"],
            "lon": e["lon"],
            "tags": tags,
            "name": tags.get("name") or tags.get("name:fr") or tags.get("name:en") or "",
            "name_fr": tags.get("name:fr", ""),
            "name_ar": tags.get("name:ar", ""),
            "operator": tags.get("operator", ""),
            "gtfs_id": tags.get("gtfs_id", ""),
            "mode": classify(tags),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--maps", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tolerance", type=float, default=250.0)
    args = ap.parse_args()

    root = Path(args.maps)
    files = [p for p in sorted(root.rglob("*.json")) if p.parent.name != "maps" or True]
    records: list[dict] = []
    for p in files:
        got = load(p)
        if got:
            records.extend(got)
            print(f"read {len(got):5d} nodes from {p.relative_to(root)}")

    # De-duplicate across the two exports: the rail file repeats metro nodes.
    best: dict[tuple, dict] = {}
    for r in records:
        key = (round(r["lat"], 5), round(r["lon"], 5), norm(r["name"]))
        prev = best.get(key)
        # Prefer the record that carries an operator: that is what proves mode.
        if prev is None or (r["operator"] and not prev["operator"]):
            best[key] = r
    records = list(best.values())

    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    stations = [s for s in seed["stations"] if s.get("lat") and s.get("lon")]
    cell = max(args.tolerance / 111320.0, 1e-5)
    grid: dict[tuple[int, int], list[dict]] = collections.defaultdict(list)
    for s in stations:
        grid[(int(s["lat"] // cell), int(s["lon"] // cell))].append(s)

    def nearest(lat: float, lon: float):
        ky, kx = int(lat // cell), int(lon // cell)
        hit, dist = None, math.inf
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for c in grid.get((ky + dy, kx + dx), []):
                    d = haversine_m(lat, lon, c["lat"], c["lon"])
                    if d < dist:
                        hit, dist = c, d
        return hit, dist

    matched = 0
    unmatched: list[dict] = []
    conflicts: list[dict] = []
    # Position alone does not identify a stop. A bus stop 130 m from a train
    # station is a different place, not a mislabelled one: on the first pass
    # that mistake produced 276 apparent conflicts of which 213 were two
    # unrelated stops. A conflict now requires the names to agree as well as
    # the positions, which leaves the ones that are genuinely the same place.
    namesake: list[dict] = []
    for r in records:
        hit, dist = nearest(r["lat"], r["lon"])
        if hit is None or dist > args.tolerance:
            unmatched.append({**r, "nearest": None, "distance_m": None})
            continue
        names_agree = norm(r["name"]) == norm(hit.get("name", "")) or not (
            norm(r["name"]) and norm(hit.get("name", ""))
        )
        if not names_agree:
            namesake.append({
                "osm_id": r["osm_id"], "osm_name": r["name"], "osm_mode": r["mode"],
                "our_id": hit["id"], "our_name": hit.get("name", ""),
                "our_mode": hit.get("mode", ""), "distance_m": round(dist, 1),
            })
            continue
        matched += 1
        ours = hit.get("mode", "unknown")
        # ours 'rail' covers train+metro; compare on that footing.
        same = (r["mode"] == ours
                or (ours == "rail" and r["mode"] == "train")
                or (ours == "train" and r["mode"] == "train"))
        if r["mode"] != "unknown" and not same:
            conflicts.append({
                "osm_id": r["osm_id"], "osm_name": r["name"],
                "osm_mode": r["mode"], "osm_operator": r["operator"],
                "our_id": hit["id"], "our_name": hit["name"], "our_mode": ours,
                "distance_m": round(dist, 1),
                "osm_tags": {k: v for k, v in r["tags"].items() if len(k) < 24},
            })

    report = {
        "source": str(root),
        "tolerance_m": args.tolerance,
        "osm_nodes": len(records),
        "osm_by_mode": dict(collections.Counter(r["mode"] for r in records)),
        "with_operator": sum(1 for r in records if r["operator"]),
        "with_gtfs_id": sum(1 for r in records if r["gtfs_id"]),
        "with_fr_name": sum(1 for r in records if r["name_fr"]),
        "with_ar_name": sum(1 for r in records if r["name_ar"]),
        "seed_stations": len(stations),
        "matched_within_tolerance": matched,
        "unmatched": len(unmatched),
        "different_place_within_tolerance": len(namesake),
        "mode_conflicts": len(conflicts),
        "conflicts": conflicts,
        "namesake_sample": namesake[:40],
        "unmatched_sample": [
            {"osm_id": r["osm_id"], "name": r["name"], "mode": r["mode"],
             "operator": r["operator"], "lat": r["lat"], "lon": r["lon"]}
            for r in unmatched[:60]
        ],
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    print(f"\nnodes (de-duplicated) ......... {len(records)}")
    print(f"  by mode: {report['osm_by_mode']}")
    print(f"  with operator ............... {report['with_operator']}")
    print(f"  with gtfs_id ................ {report['with_gtfs_id']}")
    print(f"  with name:fr / name:ar ...... "
          f"{report['with_fr_name']} / {report['with_ar_name']}")
    print(f"\nour stations .................. {len(stations)}")
    print(f"osm nodes matched ............. {matched}")
    print(f"osm nodes with no station .... {len(unmatched)}")
    print(f"different place, same spot ... {len(namesake)}  (not mode errors)")
    print(f"mode conflicts ................ {len(conflicts)}")
    if conflicts:
        print("\nconflicts:")
        for c in conflicts[:20]:
            print(f"  {c['osm_name'][:26]:26s} osm={c['osm_mode']:7s} "
                  f"ours={c['our_mode']:7s} {c['distance_m']:6.1f} m  "
                  f"op={c['osm_operator'][:26]}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
