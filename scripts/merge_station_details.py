#!/usr/bin/env python3
"""Merge station_details API data into seed_all_tunisia_routes.json.

Enriches each station with:
  - lines_served: list of {route_short_name, route_color, direction}
  - route_type: transport mode (0=RFR, 1=Metro, 2=Train, 3=Bus)
"""
import json
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

def main():
    # Load station details
    with open(BASE / "scripts/tunismapper_station_details.json", encoding="utf-8") as f:
        details = json.load(f)

    # Load existing seed
    with open(BASE / "data/seed_all_tunisia_routes.json", encoding="utf-8") as f:
        seed = json.load(f)

    # Build lookup by source_stop_id
    station_lookup = {}
    for sid, data in details["stations"].items():
        station_lookup[str(sid)] = data

    # Enrich stations
    enriched = 0
    for station in seed["stations"]:
        src_id = str(station.get("source_stop_id", ""))
        if src_id in station_lookup:
            detail = station_lookup[src_id]
            station["lines_served"] = detail.get("lines", [])
            station["route_type"] = detail.get("route_type")
            enriched += 1

    # Update metadata
    seed["metadata"]["stations_enriched"] = enriched
    seed["metadata"]["enrichment_source"] = "tunismapper station_details API"

    # Save
    out_path = BASE / "data/seed_all_tunisia_routes.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)

    print(f"Enriched {enriched}/{len(seed['stations'])} stations with line details")
    print(f"Saved -> {out_path}")

if __name__ == "__main__":
    main()
