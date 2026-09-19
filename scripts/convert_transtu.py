#!/usr/bin/env python3
"""Convert Tunismapper Transtu bus routes to bledi.tn seed format."""
import json, re, hashlib
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def parse_route_name(name):
    """Parse 'Origin - Destination' route name into two station names."""
    # Common Arabic/French separators
    for sep in [" — ", " - ", " – "]:
        if sep in name:
            parts = name.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    # No separator found
    return name.strip(), ""

def main():
    # Load Tunismapper data
    with open(BASE / "scripts/transtu_all_bus_routes.json", encoding="utf-8") as f:
        tunismapper = json.load(f)

    routes = tunismapper["routes"]
    print(f"Processing {len(routes)} Transtu routes...")

    # Build stations set
    stations = {}
    for r in routes:
        short = r.get("route_short_name", "?").strip()
        long_name = r.get("route_long_name", "")
        origin, dest = parse_route_name(long_name)

        for city in [origin, dest]:
            if city and city not in stations:
                stations[city] = {
                    "id": slugify(city),
                    "name": city,
                    "name_ar": city,  # TODO: add Arabic names if available
                    "name_en": city,
                    "governorate": "Tunis",  # Transtu serves Grand Tunis
                }

    # Build lines in seed format
    seed_lines = []
    for r in routes:
        short = r.get("route_short_name", "?").strip()
        long_name = r.get("route_long_name", "")
        origin, dest = parse_route_name(long_name)
        route_id = r.get("route_id", "")
        color = r.get("route_color", "")

        origin_id = slugify(origin) if origin else "unknown"
        dest_id = slugify(dest) if dest else "unknown"

        # Parse line number (strip letters for numeric)
        num_match = re.match(r"^(\d+)", short)
        line_num = num_match.group(1) if num_match else short

        entry = {
            "id": f"transtu_{route_id}_{slugify(short)}",
            "number": short,
            "name": f"Ligne {short}: {long_name}",
            "operator": "Transtu",
            "mode": "bus",
            "type": "urban",
            "description": long_name,
            "color": color,
            "stations": [origin_id, dest_id],
            "api_id": route_id,
            "api_source": "tunismapper",
        }
        seed_lines.append(entry)

    # Load existing seed
    seed_path = BASE / "data/seed_lines_bizerte.json"
    with open(seed_path, encoding="utf-8") as f:
        existing = json.load(f)

    # Preserve lines from OTHER operators that may already be in the seed
    keep_lines = [l for l in existing["lines"] if l.get("operator") != "Transtu"]

    # Add Transtu lines to seed
    existing_station_ids = {s["id"] for s in existing["stations"]}
    added_stations = 0
    for s in stations.values():
        if s["id"] not in existing_station_ids:
            existing["stations"].append(s)
            added_stations += 1

    existing["lines"] = keep_lines + seed_lines
    existing["metadata"]["total_lines"] = len(existing["lines"])
    existing["metadata"]["operators"] = existing["metadata"].get("operators", {})
    existing["metadata"]["operators"]["Transtu"] = {
        "website": "https://www.transtu.tn",
        "coverage": "Grand Tunis (Tunis, Ariana, Manouba, Ben Arous)",
        "line_count": len(seed_lines),
        "source": "Tunismapper API (tunismapper.com)",
        "extracted_date": "2026-09-19",
    }

    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"\nAdded {len(seed_lines)} Transtu lines")
    print(f"Added {added_stations} new stations")
    print(f"Total lines: {len(existing['lines'])} (131 Bizerte + 190 Transtu)")
    print(f"Total stations: {len(existing['stations'])}")

    # Update all_tunisia_bus_registry.json
    reg_path = BASE / "data/all_tunisia_bus_registry.json"
    with open(reg_path, encoding="utf-8") as f:
        reg = json.load(f)

    reg["operators"]["Transtu"] = {
        "website": "https://www.transtu.tn",
        "coverage": "Grand Tunis (Tunis, Ariana, Manouba, Ben Arous)",
        "line_count": len(seed_lines),
        "source": "Tunismapper API (tunismapper.com)",
        "lines": [{
            "number": l["number"],
            "name": l["name"],
            "type": l["type"],
        } for l in seed_lines],
    }
    reg["metadata"]["total_operators"] = len(reg["operators"])
    reg["metadata"]["total_lines"] = sum(op["line_count"] for op in reg["operators"].values())

    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    print(f"Updated registry: {reg['metadata']['total_operators']} operators, {reg['metadata']['total_lines']} total lines")

if __name__ == "__main__":
    main()
