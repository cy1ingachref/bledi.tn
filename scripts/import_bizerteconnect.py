#!/usr/bin/env python3
"""Import BizerteConnect stations and link lines to make them routable.

Source: C:\\Users\\cy1in\\Downloads\\tunisia-transport-data\\
        06-docs-tools\\TunisiaTransport-repo\\data\\seed_lines_bizerte.json
  - 1,498 stations with lat/lon
  - 320 lines with station references

Target: data/seed_all_tunisia_routes.tagged.json
  - 117 BizerteConnect lines currently have 0 stations, routable=false

Usage:
    python scripts/import_bizerteconnect.py --dry-run
    python scripts/import_bizerteconnect.py --write
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
BIZ_SOURCE = Path(
    r"C:\Users\cy1in\Downloads\tunisia-transport-data"
    r"\06-docs-tools\TunisiaTransport-repo\data\seed_lines_bizerte.json"
)

TOLERANCE_M = 150.0
CELL = 0.002  # ~220 m grid cell


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
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

    if not BIZ_SOURCE.exists():
        print(f"ERROR: not found: {BIZ_SOURCE}", file=sys.stderr)
        return 2

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    biz = json.loads(BIZ_SOURCE.read_text(encoding="utf-8"))

    biz_stations = biz.get("stations", [])
    biz_lines = biz.get("lines", [])

    print(f"BizerteConnect source: {len(biz_stations)} stations, {len(biz_lines)} lines")
    print(f"Seed: {len(seed['stations'])} stations, {len(seed['lines'])} lines")

    # --- Step 1: Build a proximity index of existing seed stations ---
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for s in seed["stations"]:
        la, lo = s.get("lat"), s.get("lon")
        if la and lo:
            grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    def is_known(la: float, lo: float) -> bool:
        ci, cj = round(la / CELL), round(lo / CELL)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for sla, slo in grid.get((ci + di, cj + dj), ()):
                    if haversine(la, lo, sla, slo) <= TOLERANCE_M:
                        return True
        return False

    # --- Step 2: Import new BizerteConnect stations ---
    existing_ids = {s["id"] for s in seed["stations"]}
    added_stations: list[dict] = []
    skipped_dup = 0

    for bs in biz_stations:
        la, lo = bs.get("lat"), bs.get("lon")
        if not la or not lo or la == 0 or lo == 0:
            continue
        if is_known(la, lo):
            skipped_dup += 1
            continue

        name_fr = bs.get("name_fr") or bs.get("name_ar") or bs.get("id", "")
        name_en = bs.get("name_en") or name_fr
        sid = f"bc_{bs['id']}"
        if sid in existing_ids:
            skipped_dup += 1
            continue

        station_type = bs.get("type", "bus_stop")
        mode = "bus" if "bus" in station_type else "unknown"

        added_stations.append({
            "id": sid,
            "name": name_fr,
            "name_en": name_en,
            "lat": la,
            "lon": lo,
            "mode": mode,
            "operator": "BizerteConnect",
            "lines_served": [],
            "route_type": 3 if mode == "bus" else 0,
            "source": "bizerteconnect-api",
            "license_status": "official-public",
        })
        existing_ids.add(sid)
        grid.setdefault((round(la / CELL), round(lo / CELL)), []).append((la, lo))

    print(f"\nStations: {len(added_stations)} new, {skipped_dup} duplicates skipped")

    # --- Step 3: Link BizerteConnect lines to stations ---
    # Build a lookup from station ID to station
    station_by_id = {s["id"]: s for s in seed["stations"]}
    for s in added_stations:
        station_by_id[s["id"]] = s

    # Build a lookup from line number to seed line
    seed_bc_lines = [l for l in seed["lines"] if l.get("source") == "bizerteconnect-api"]
    seed_by_number: dict[str, dict] = {}
    for l in seed_bc_lines:
        num = l.get("number", "")
        if num:
            seed_by_number[str(num)] = l

    linked_count = 0
    unlinked_count = 0

    for bl in biz_lines:
        line_number = str(bl.get("number", ""))
        if not line_number or line_number not in seed_by_number:
            continue

        seed_line = seed_by_number[line_number]
        biz_station_ids = bl.get("stations", [])

        # Resolve station references - biz uses bare IDs like "bizerte", "ain_el_berda"
        # Our imported stations use "bc_bizerte", "bc_ain_el_berda", etc.
        resolved = []
        for sid in biz_station_ids:
            # Try direct match first
            if sid in station_by_id:
                resolved.append(sid)
            # Try with bc_ prefix
            elif f"bc_{sid}" in station_by_id:
                resolved.append(f"bc_{sid}")

        if resolved:
            seed_line["stations"] = resolved
            seed_line["routable"] = True
            # Update mode if needed
            if seed_line.get("mode") == "unknown":
                seed_line["mode"] = "bus"
            linked_count += 1

            # Update lines_served on stations
            for sid in resolved:
                station = station_by_id[sid]
                if line_number not in station.get("lines_served", []):
                    station.setdefault("lines_served", []).append(line_number)
        else:
            unlinked_count += 1

    print(f"Lines: {linked_count} linked to stations, {unlinked_count} unresolved")

    # --- Step 4: Report ---
    total_bc_stations = len([s for s in seed["stations"] if s.get("source") == "bizerteconnect-api"])
    total_bc_lines = len([l for l in seed["lines"] if l.get("source") == "bizerteconnect-api"])
    routable_bc_lines = len([l for l in seed["lines"] if l.get("source") == "bizerteconnect-api" and l.get("routable")])

    print(f"\nResult: {total_bc_stations} BizerteConnect stations, {total_bc_lines} lines, {routable_bc_lines} routable")

    if args.dry_run:
        print("\n--dry-run: seed NOT modified.")
        if added_stations:
            print(f"\nSample new stations (first 10):")
            for s in added_stations[:10]:
                print(f"  + {s['id']:40} {s['name'][:40]:42} {s['lat']},{s['lon']}")
        return 0

    # --- Step 5: Write ---
    seed["stations"] = seed["stations"] + added_stations
    md = seed.setdefault("metadata", {})
    md["bizerteconnect_import"] = {
        "source": str(BIZ_SOURCE),
        "stations_added": len(added_stations),
        "stations_skipped_dup": skipped_dup,
        "lines_linked": linked_count,
        "lines_unlinked": unlinked_count,
        "note": "BizerteConnect stations imported from Downloads; lines linked to stations and marked routable.",
    }

    SEED.write_text(
        json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nWrote {SEED} ({len(seed['stations'])} stations, {len(seed['lines'])} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
