#!/usr/bin/env python3
"""Convert BizerteConnect API data to bledi.tn seed format + full registry."""
import json, re, hashlib
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")

def main():
    # Load API data
    with open(BASE / "scripts/bizerteconnect_all_lines.json", encoding="utf-8") as f:
        lines = json.load(f)

    print(f"Processing {len(lines)} BizerteConnect lines...")

    # Build stations set
    stations = {}
    for line in lines:
        for key in ["origin", "destination"]:
            name = line.get(key) or line.get(f"{key}_en") or line.get(f"{key}_ar")
            if name and name not in stations:
                stations[name] = {
                    "id": slugify(name),
                    "name": name,
                    "name_ar": line.get(f"{key}_ar", name),
                    "name_en": line.get(f"{key}_en", name),
                }

    # Build lines in seed format
    seed_lines = []
    for line in lines:
        origin = line.get("origin") or line.get("origin_en") or "?"
        dest = line.get("destination") or line.get("destination_en") or "?"
        ltype = line.get("type", "INTERNAL")
        num = line.get("number", "?")

        # Determine mode type
        if ltype == "EXTERNAL":
            line_type = "inter_governorate"
        else:
            line_type = "intra_governorate"

        # Station refs
        origin_id = slugify(origin)
        dest_id = slugify(dest)
        line_stations = [origin_id, dest_id]

        entry = {
            "id": f"biz_{slugify(f'{num}_{origin}_{dest}')}",
            "number": num,
            "name": line.get("name", f"Ligne {origin} - {dest}"),
            "operator": "BizerteConnect",
            "mode": "bus",
            "type": line_type,
            "description": line.get("name_en", ""),
            "stations": line_stations,
            "api_id": line.get("id"),
        }
        seed_lines.append(entry)

    # Save expanded seed
    # First load existing seed to merge
    seed_path = BASE / "data/seed_lines_bizerte.json"
    with open(seed_path, encoding="utf-8") as f:
        existing = json.load(f)

    # Merge: add new stations, replace lines with full set
    existing_station_ids = {s["id"] for s in existing["stations"]}
    for s in stations.values():
        if s["id"] not in existing_station_ids:
            existing["stations"].append(s)

    existing["lines"] = seed_lines
    existing["metadata"]["total_lines"] = len(seed_lines)
    existing["metadata"]["source"] = "BizerteConnect API v1 (bizerteconnect.com)"

    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    print(f"Updated seed_lines_bizerte.json: {len(seed_lines)} lines, {len(existing['stations'])} stations")

    # Also save a comprehensive ALL-Tunisia bus registry
    registry = {
        "metadata": {
            "source": "bledi.tn comprehensive extraction",
            "date": "2026-09-19",
            "operators": {},
        },
        "operators": {
            "BizerteConnect": {
                "website": "https://www.bizerteconnect.com",
                "coverage": "Bizerte governorate (internal + external)",
                "line_count": len(seed_lines),
                "lines": [{
                    "number": l["number"],
                    "name": l["name"],
                    "type": l["type"],
                    "origin": lines[i].get("origin", "?"),
                    "destination": lines[i].get("destination", "?"),
                } for i, l in enumerate(seed_lines)],
            }
        }
    }

    reg_path = BASE / "data/all_tunisia_bus_registry.json"
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    print(f"Saved registry -> {reg_path}")

if __name__ == "__main__":
    main()
