#!/usr/bin/env python3
"""Import the Downloads transport exports into the seed dataset.

The Downloads folder (C:\\Users\\cy1in\\Downloads\\transport) holds the operator
exports that were collected for this project: TRANSTU/SNTRI/SNCFT/SORETRAS/
SRTGN/SRTJ/SRTM/TGM stop lists, GTFS feeds, and a geolocated stop file.

This importer is deliberately conservative. It only adds stops that are
genuinely NEW -- more than TOLERANCE_M from every station already in the seed --
because the seed already covers the vast majority of these exports and
duplicating them would inflate the counts without improving routing.

It does NOT import the 350 `rural_lines` from _network.json. Those have
`mapped: false` and their stops are bare Arabic place names with no
coordinates, so they cannot be routed; importing them would add line records
that no itinerary could ever use. What they need is geocoding, which is a
separate task.

Usage:
    python scripts/import_downloads_stops.py --dry-run
    python scripts/import_downloads_stops.py --write
"""
from __future__ import annotations

import argparse
import os
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
DOWNLOADS = Path(os.environ.get("BLEDI_TRANSPORT_DUMP",
                              Path.home() / "Downloads" / "transport"))
GEOLOCATED = DOWNLOADS / "_geolocated.json"

TOLERANCE_M = 150.0
CELL = 0.002  # ~220 m grid cell for the proximity index


def haversine(a: float, b: float, c: float, d: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(a), math.radians(c)
    dp = p2 - p1
    dl = math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in text]
    out = "".join(keep)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:48] or "stop"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.write):
        ap.error("pass --dry-run or --write")

    if not GEOLOCATED.exists():
        print(f"ERROR: not found: {GEOLOCATED}", file=sys.stderr)
        return 2

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    geo = json.loads(GEOLOCATED.read_text(encoding="utf-8"))

    stations = seed["stations"]
    existing = {
        (s["lat"], s["lon"])
        for s in stations
        if s.get("lat") and s.get("lon")
    }

    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for la, lo in existing:
        grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    def is_known(la: float, lo: float) -> bool:
        ci, cj = round(la / CELL), round(lo / CELL)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo in grid.get((ci + di, cj + dj), ()):
                    if haversine(la, lo, sla, slo) <= TOLERANCE_M:
                        return True
        return False

    existing_ids = {s["id"] for s in stations}
    added: list[dict] = []
    skipped_dup = skipped_bad = 0

    for g in geo:
        la, lo = g.get("lat"), g.get("lon")
        if not la or not lo or la == 0 or lo == 0:
            skipped_bad += 1
            continue
        if is_known(la, lo):
            skipped_dup += 1
            continue

        name = (g.get("name") or "").strip() or "Arrêt sans nom"
        mode = str(g.get("mode") or "bus").lower()
        op = str(g.get("operator") or "").upper()
        sid = f"dl_{slug(op)}_{slug(name)}_{abs(hash((round(la, 5), round(lo, 5)))) % 100000:05d}"
        if sid in existing_ids:
            skipped_dup += 1
            continue

        added.append({
            "id": sid,
            "name": name,
            "name_en": name,
            "lat": la,
            "lon": lo,
            "mode": mode,
            "operator": op,
            "lines_served": [],
            "route_type": 3 if mode == "bus" else 2,
            "source": "downloads-transport-export",
            "license_status": "official-public",
            "governorate": g.get("governorate", ""),
        })
        existing_ids.add(sid)
        # register so later duplicates in the same file are caught
        grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    by_mode: dict[str, int] = {}
    for a in added:
        by_mode[a["mode"]] = by_mode.get(a["mode"], 0) + 1

    print(f"seed stations            : {len(stations)}")
    print(f"downloads geolocated     : {len(geo)}")
    print(f"skipped (already covered): {skipped_dup}")
    print(f"skipped (bad coords)     : {skipped_bad}")
    print(f"NEW stops to add         : {len(added)}")
    for m, n in sorted(by_mode.items(), key=lambda x: -x[1]):
        print(f"    {m}: {n}")

    if not added:
        print("\nNothing to add.")
        return 0

    if args.dry_run:
        print("\n--dry-run: seed NOT modified.")
        for a in added[:10]:
            print(f"  + {a['mode']:6s} {a['name'][:44]:46s} {a['lat']},{a['lon']}")
        if len(added) > 10:
            print(f"  ... and {len(added) - 10} more")
        return 0

    # Merge, keeping the seed's own ordering and metadata.
    seed["stations"] = stations + added
    md = seed.setdefault("metadata", {})
    md["total_stations"] = len(seed["stations"])
    md["downloads_import"] = {
        "source": str(GEOLOCATED),
        "added": len(added),
        "by_mode": by_mode,
        "tolerance_m": TOLERANCE_M,
        "note": "Only stops >150 m from any existing station were added.",
    }
    SEED.write_text(
        json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nWrote {SEED} ({len(seed['stations'])} stations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
