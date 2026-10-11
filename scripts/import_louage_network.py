#!/usr/bin/env python3
"""Import the Tunisia louage network CSV into the seed dataset.

The CSV (C:\\Users\\cy1in\\Downloads\\tunisia_louage_network.csv) contains 13
louage stations spanning the whole country, each with real coordinates, a
list of destinations served, and the highway corridor used.

This importer:
  1. Adds all 13 stations with mode='louage'
  2. Creates louage-to-louage lines between stations that share destinations
  3. Connects each louage station to the nearest existing seed station for
     network access (so you can route from a louage station to anywhere)

The Bizerte station has a missing longitude in the CSV; we use the known
value 9.8722566 from the earlier Google Places export.

Usage:
    python scripts/import_louage_network.py --dry-run
    python scripts/import_louage_network.py --write
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
CSV_PATH = Path.home() / "Downloads" / "tunisia_louage_network.csv"

# Known Bizerte longitude from the Google Places export
BIZERTE_LON = 9.8722566


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
    return out.strip("_")[:48] or "station"


def normalize(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.write):
        ap.error("pass --dry-run or --write")

    if not CSV_PATH.exists():
        print(f"ERROR: not found: {CSV_PATH}", file=sys.stderr)
        return 2

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    stations = seed["stations"]
    lines = seed["lines"]

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"CSV: {len(rows)} louage stations")
    print(f"Seed: {len(stations)} stations, {len(lines)} lines")

    # Build a lookup of existing stations by normalized name
    existing_by_norm = {}
    for s in stations:
        n = normalize(s.get("name", ""))
        if n:
            existing_by_norm[n] = s

    # Parse CSV rows
    csv_stations = []
    for row in rows:
        name = row["Station Name"].strip()
        lat = float(row["Latitude"])
        lon_str = row["Longitude"].strip()
        lon = float(lon_str) if lon_str else BIZERTE_LON
        dests = [d.strip() for d in row["Destinations Served"].split(",") if d.strip()]
        corridor = row["Route Corridor"].strip()
        csv_stations.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "destinations": dests,
            "corridor": corridor,
        })

    # Check which already exist
    new_stations = []
    for cs in csv_stations:
        norm = normalize(cs["name"])
        if norm in existing_by_norm:
            print(f"  EXISTS  {cs['name']}")
        else:
            new_stations.append(cs)
            print(f"  NEW     {cs['name']} ({cs['lat']},{cs['lon']})")

    if not new_stations:
        print("\nAll stations already exist. Nothing to add.")
        return 0

    # Add new stations
    station_ids = {}
    for cs in new_stations:
        sid = f"louage_{slug(cs['name'])}"
        station_ids[cs["name"]] = sid
        stations.append({
            "id": sid,
            "name": cs["name"],
            "name_en": cs["name"],
            "lat": cs["lat"],
            "lon": cs["lon"],
            "mode": "louage",
            "operator": "louage",
            "lines_served": [],
            "route_type": 3,
            "source": "tunisia_louage_network.csv",
            "license_status": "user-compiled",
            "destinations_served": cs["destinations"],
            "corridor": cs["corridor"],
        })

    # Build louage-to-louage lines: connect stations that share destinations
    # First, map destination names to CSV station names
    dest_to_csv = {}
    for cs in csv_stations:
        for d in cs["destinations"]:
            dest_to_csv.setdefault(d, []).append(cs["name"])

    # Also map destination names to existing seed stations
    dest_to_seed = {}
    for s in stations:
        n = normalize(s.get("name", ""))
        if n:
            dest_to_seed.setdefault(n, []).append(s)

    # Track which station pairs already have a line (dedup key)
    existing_pairs = set()
    for l in lines:
        stops = l.get("stations") or []
        if len(stops) >= 2:
            pair = tuple(sorted([stops[0], stops[-1]]))
            existing_pairs.add(pair)

    # Create lines: for each CSV station, connect to nearest CSV station in each
    # destination city that is also a CSV station
    new_lines = []
    line_num = 0
    for cs in csv_stations:
        for dest in cs["destinations"]:
            # Find CSV stations in this destination
            csv_dests = [n for n in dest_to_csv.get(dest, []) if n != cs["name"]]
            if not csv_dests:
                continue
            # Pick the nearest one
            best = None
            best_dist = float("inf")
            for dn in csv_dests:
                dcs = next(x for x in csv_stations if x["name"] == dn)
                dist = haversine(cs["lat"], cs["lon"], dcs["lat"], dcs["lon"])
                if dist < best_dist:
                    best_dist = dist
                    best = dn
            if best:
                sid_a = station_ids.get(cs["name"])
                sid_b = station_ids.get(best)
                if not sid_a or not sid_b:
                    continue
                pair = tuple(sorted([sid_a, sid_b]))
                if pair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                line_num += 1
                line_id = f"louage_{line_num:03d}_{slug(cs['name'][:15])}_{slug(best[:15])}"
                new_lines.append({
                    "id": line_id,
                    "number": f"L{line_num}",
                    "name": f"Louage: {cs['name']} → {best}",
                    "operator": "louage",
                    "mode": "louage",
                    "type": "intercity",
                    "route_id": str(line_num),
                    "stations": [sid_a, sid_b],
                    "departures": [],
                    "source": "tunisia_louage_network.csv",
                    "license_status": "user-compiled",
                    "corridor": cs["corridor"],
                })

    # Also connect each new louage station to the nearest existing seed station
    # for network access
    for cs in new_stations:
        best = None
        best_dist = float("inf")
        for s in stations:
            if s["id"] in station_ids.values():
                continue  # skip other new louage stations
            if not s.get("lat") or not s.get("lon"):
                continue
            dist = haversine(cs["lat"], cs["lon"], s["lat"], s["lon"])
            if dist < best_dist:
                best_dist = dist
                best = s
        if best and best_dist < 50000:  # only if within 50km
            line_num += 1
            sid_a = station_ids[cs["name"]]
            sid_b = best["id"]
            line_id = f"louage_access_{line_num:03d}_{slug(cs['name'][:20])}"
            new_lines.append({
                "id": line_id,
                "number": f"LA{line_num}",
                "name": f"Louage access: {cs['name']} → {best['name']}",
                "operator": "louage",
                "mode": "louage",
                "type": "access",
                "route_id": str(line_num),
                "stations": [sid_a, sid_b],
                "departures": [],
                "source": "tunisia_louage_network.csv",
                "license_status": "user-compiled",
                "corridor": cs["corridor"],
                "note": f"Access connection to nearest transit station ({best['name']}, {best_dist:.0f}m)",
            })

    print(f"\nNew stations: {len(new_stations)}")
    print(f"New lines: {len(new_lines)}")
    for l in new_lines[:10]:
        print(f"  {l['id'][:50]:52s} {l['name'][:60]}")
    if len(new_lines) > 10:
        print(f"  ... and {len(new_lines) - 10} more")

    if args.dry_run:
        print("\n--dry-run: seed NOT modified.")
        return 0

    # Write
    seed["stations"] = stations
    seed["lines"] = lines + new_lines
    md = seed.setdefault("metadata", {})
    md["total_stations"] = len(stations)
    md["total_lines"] = len(seed["lines"])
    md["louage_import"] = {
        "source": str(CSV_PATH),
        "stations_added": len(new_stations),
        "lines_added": len(new_lines),
        "note": "National louage network from tunisia_louage_network.csv",
    }
    SEED.write_text(
        json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nWrote {SEED} ({len(stations)} stations, {len(seed['lines'])} lines).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
