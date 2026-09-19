#!/usr/bin/env python3
"""Parse Tebourba PDF timetable and add missing lines to the dataset."""
import json
import re
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")


def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


# Parsed from Tebourba.pdf (summer 2018 timetable)
LINES = [
    {"number": "116", "name": "Bab Alioua - Tebourba", "route": "Bab Alioua → Tebourba",
     "times": {"to": "05:30", "from": "04:50", "last_to": "18:15", "last_from": "17:30"}},
    {"number": "542", "name": "Tebourba - El Sherouia", "route": "Tebourba → El Sherouia",
     "times": {"to": "06:50", "from": "05:20", "last_to": "17:30", "last_from": "16:00"}},
    {"number": "16B", "name": "Khaireddine Basha - Tebourba", "route": "Khaireddine Basha → Tebourba",
     "times": {"to": "05:10", "from": "06:00", "last_to": "18:30", "last_from": "19:20"}},
    {"number": "42B", "name": "Khaireddine Basha - Tebourba (via Zouitine)", "route": "Khaireddine Basha → Zouitine → Tebourba",
     "times": {"to": "05:00", "from": "05:50", "last_to": "20:20", "last_from": "19:40"}},
    {"number": "42", "name": "Menzel Belhouane - Mansoura - Tebourba", "route": "Menzel Belhouane → Mansoura → Tebourba",
     "times": {}},
    {"number": "42A", "name": "Menzel Belhouane - Mansoura", "route": "Menzel Belhouane → Mansoura",
     "times": {}},
    {"number": "46", "name": "Tebourba - Borj Touri", "route": "Tebourba → Borj Touri",
     "times": {"to": "04:50", "from": "05:20", "last_to": "19:40", "last_from": "19:00"}},
    {"number": "66", "name": "Tebourba - El Dakhila", "route": "Tebourba → El Dakhila",
     "times": {"to": "04:50", "from": "05:20", "last_to": "19:40", "last_from": "19:00"}},
    {"number": "49", "name": "Hopital Tebourba - El Batan", "route": "Hopital Tebourba → El Batan",
     "times": {"to": "06:40", "from": "06:00"}},
    {"number": "42C", "name": "Tebourba - Zone Industrielle Manouba", "route": "Tebourba → Zone Industrielle Manouba",
     "times": {"to": "06:45", "from": "05:45", "last_to": "17:45", "last_from": "16:45"}},
    {"number": "94", "name": "Slimen Kahia - Tebourba (via Borj El Amri)", "route": "Slimen Kahia → Borj El Amri → Tebourba",
     "times": {"to": "07:00", "from": "08:00", "last_to": "18:00", "last_from": "17:00"}},
    {"number": "98", "name": "Khaireddine Basha - Tebourba (via Jelou)", "route": "Khaireddine Basha → Jelou → Tebourba",
     "times": {"to": "05:20", "from": "06:10", "last_to": "17:10", "last_from": "18:00"}},
]


def main():
    seed_path = BASE / "data/seed_all_tunisia_routes.json"
    with open(seed_path, encoding="utf-8") as f:
        seed = json.load(f)

    existing_nums = {l["number"] for l in seed["lines"]}
    new_lines_data = [l for l in LINES if l["number"] not in existing_nums]

    print(f"New lines to add: {len(new_lines_data)}")
    for l in new_lines_data:
        print(f"  {l['number']}: {l['route']}")

    # Add new stations and lines
    added = 0
    for line_data in new_lines_data:
        route_parts = line_data["route"].split(" → ")
        station_ids = []
        for part in route_parts:
            sid = slugify(part)
            station_ids.append(sid)
            if sid not in {s["id"] for s in seed["stations"]}:
                seed["stations"].append({
                    "id": sid,
                    "name": part,
                    "lat": 0,
                    "lon": 0,
                    "mode": "bus",
                    "operator": "Transtu",
                })

        line_entry = {
            "id": f"transtu_tebourba_{slugify(line_data['number'])}",
            "number": line_data["number"],
            "name": line_data["name"],
            "operator": "Transtu",
            "mode": "bus",
            "type": "intercity",
            "description": line_data["route"],
            "stations": station_ids,
            "schedule": line_data["times"],
            "source": "transtu.com.tn PDF (Tebourba.pdf)",
        }
        seed["lines"].append(line_entry)
        added += 1

    seed["metadata"]["total_lines"] = len(seed["lines"])
    seed["metadata"]["tebourba_lines_added"] = added
    seed["metadata"]["last_updated"] = "2026-09-19"

    with open(seed_path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)

    print(f"\nAdded {added} new lines to seed")
    print(f"Seed now: {len(seed['lines'])} lines, {len(seed['stations'])} stations")


if __name__ == "__main__":
    main()
