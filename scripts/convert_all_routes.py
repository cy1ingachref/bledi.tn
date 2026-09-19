#!/usr/bin/env python3
"""Convert scraped Tunismapper stop data (all modes) into bledi.tn seed format.

Reads tunismapper_all_routes_stops.json (bus + train + metro + RFR with GPS,
schedules, and stop metadata), builds unified station registry with coordinates,
and writes seed_all_tunisia_routes.json for bledi.tn import.
"""
import json, re, time
from pathlib import Path
from collections import Counter

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

MODE_TO_TYPE = {
    "Bus": "bus",
    "Train": "train",
    "Métro": "metro",
    "RFR": "rail",
}
OPERATOR_MAP = {
    "Bus": "Transtu",
    "Train": "SNCFT",
    "Métro": "Transtu",
    "RFR": "Transtu",
}

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def main():
    # Load scraped routes
    with open(BASE / "scripts/tunismapper_all_routes_stops.json", encoding="utf-8") as f:
        scraped = json.load(f)

    routes = scraped["routes"]
    print(f"Processing {len(routes)} Tunismapper routes across all modes...")

    # Build unified station registry and line entries
    stations = {}
    lines = []
    stats = Counter()

    for route in routes:
        route_id = route["route_id"]
        mode = route["transport_type"]
        number = route["route_number"]
        stops_data = route.get("stops", [])

        if not stops_data:
            continue

        operator = OPERATOR_MAP.get(mode, "Transtu")
        mode_type = MODE_TO_TYPE.get(mode, "unknown")
        stats[mode] += 1

        # Collect departures from first stop that has them
        departures = []
        for stop in stops_data:
            if stop.get("horaires"):
                departures = [h.get("time", "") for h in stop["horaires"] if h.get("time")]
                break

        # Build ordered station list
        station_ids = []
        for stop in stops_data:
            name = stop.get("name", "").strip()
            if not name:
                continue

            stop_slug = slugify(name)
            # Include route_id in station ID to avoid collisions between modes
            station_id = f"{stop_slug}"

            if station_id not in stations:
                stations[station_id] = {
                    "id": station_id,
                    "name": name,
                    "name_en": name,
                    "lat": float(stop.get("lat", 0)),
                    "lon": float(stop.get("lon", 0)),
                    "source_stop_id": stop.get("stop_id", ""),
                    "mode": mode_type,
                    "operator": operator,
                }
            station_ids.append(station_id)

        if not station_ids:
            continue

        # Build line entry
        direction_name = stops_data[-1].get("name", "") if stops_data else ""
        line_name = f"Ligne {number}: {stops_data[0].get('name','')} - {direction_name}" if stops_data else f"Ligne {number}"

        line_entry = {
            "id": f"{mode_type}_{route_id}_{slugify(number)}",
            "number": number,
            "name": line_name,
            "operator": operator,
            "mode": mode_type,
            "type": "urban" if mode_type in ("bus", "metro") else "intercity",
            "route_id": route_id,
            "stations": station_ids,
            "departures": departures[:30],
            "source": "tunismapper",
        }
        lines.append(line_entry)

    # Build final seed structure
    seed = {
        "metadata": {
            "source": "Tunismapper (tunismapper.com ligne_details.php)",
            "extracted_date": "2026-09-19",
            "total_lines": len(lines),
            "total_stations": len(stations),
            "by_mode": dict(stats),
            "coordinate_coverage": sum(
                1 for s in stations.values() if s.get("lat") and s.get("lon")
            ),
        },
        "stations": list(stations.values()),
        "lines": lines,
    }

    # Write
    out_path = BASE / "data/seed_all_tunisia_routes.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)

    print(f"\n=== Conversion Complete ===")
    print(f"Total lines: {len(lines)}")
    print(f"Total stations: {len(stations)}")
    print(f"Stations with GPS: {seed['metadata']['coordinate_coverage']}")
    print(f"\nBy mode:")
    for mode, count in sorted(stats.items()):
        mode_stops = sum(len(l["stations"]) for l in lines if l["mode"] == MODE_TO_TYPE.get(mode, ""))
        print(f"  {mode}: {count} routes, {mode_stops} stops")
    print(f"\nSaved -> {out_path}")

if __name__ == "__main__":
    main()
