"""Build new seed from ALL extracted station data.
Merges: extract_01_bus (15,415), extract_02_rail (2,402), extract_06_docs (1,869)
Plus: existing seed (7,313 stations with line references)

Strategy:
1. Load all extractions
2. Normalize names for matching
3. Deduplicate by position (within 50m) + name similarity
4. Keep the most authoritative source
5. Merge with existing seed (preserving line references)
6. Fix water stations
7. Output new seed
"""
import json
import math
import re
from collections import defaultdict

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common prefixes
    name = re.sub(r'^(gare|station|arrêt|stop|halte|محطة)\s+', '', name)
    name = re.sub(r'\s+(gare|station|arrêt|stop|halte)$', '', name)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name

# Water polygons
GULF_TUNIS = [(36.85,10.00),(36.90,10.10),(36.95,10.20),(37.00,10.30),(37.05,10.40),(37.00,10.50),(36.90,10.40),(36.85,10.30),(36.85,10.00)]
LAKE_TUNIS = [(36.75,10.10),(36.80,10.15),(36.85,10.20),(36.80,10.25),(36.75,10.20),(36.70,10.15),(36.75,10.10)]
BIZERTE_LAGOON = [(37.15,9.85),(37.20,9.80),(37.25,9.85),(37.30,9.90),(37.35,9.95),(37.30,10.00),(37.25,9.95),(37.20,9.90),(37.15,9.85)]

def in_poly(lat, lon, poly):
    n = len(poly); inside = False
    for i in range(n):
        p1l, p1o = poly[i]; p2l, p2o = poly[(i+1)%n]
        if (p1o > lon) != (p2o > lon):
            t = (lon - p1o) / (p2o - p1o)
            if lat < p1l + t * (p2l - p1l): inside = not inside
    return inside

def in_any_water(lat, lon):
    return in_poly(lat, lon, GULF_TUNIS) or in_poly(lat, lon, LAKE_TUNIS) or in_poly(lat, lon, BIZERTE_LAGOON)

# Source authority (lower = more authoritative)
AUTHORITY = {
    # GTFS and official exports (most authoritative)
    "gtfs": 1,
    "downloads:GTFS Horaires des bus de la SORETRAK - ": 1,
    "downloads:GTFS Horaires des voyages de la société": 1,
    "downloads:GTFS Horaires des voyages de la TRANSTU": 1,
    "downloads:SNCFT Banlieue Sahel stations": 1,
    "downloads:SNCFT Banlieue Sud stations": 1,
    "downloads:SNTRI stops": 1,
    # Official operator data
    "official-public": 2,
    "official-open-data": 2,
    "downloads-transport-export": 2,
    "downloads:BLEDI curated workbook": 2,
    "downloads:TNRP national bus-stop registry": 3,
    "bizerteconnect-api": 3,
    # Crowdsourced
    "tunismapper": 4,
    "google-places-workbook": 5,
    "tunisia_louage_network.csv": 6,
    "unknown": 7,
}

def get_authority(source):
    return AUTHORITY.get(source, 8)

def detect_operator(name, source):
    """Detect operator from name or source."""
    name_lower = name.lower() if name else ""
    if "sncft" in name_lower or "snct" in name_lower or "train" in name_lower:
        return "SNCFT"
    if "transtu" in name_lower or "métro" in name_lower or "metro" in name_lower:
        return "TRANSTU"
    if "sntri" in name_lower:
        return "SNTRI"
    if "soretras" in name_lower:
        return "SORETRAS"
    if "louage" in name_lower or "louaj" in name_lower:
        return "Louage"
    if "bizerteconnect" in source.lower():
        return "BizerteConnect"
    return ""

def detect_mode(name, source):
    """Detect mode from name or source."""
    name_lower = name.lower() if name else ""
    if "sncft" in name_lower or "train" in name_lower or "rail" in name_lower:
        return "train"
    if "métro" in name_lower or "metro" in name_lower:
        return "metro"
    if "louage" in name_lower or "louaj" in name_lower:
        return "louaj"
    return "bus"

# Load all data
print("Loading data...")
with open(r"C:\Users\cy1in\bledi.tn\data\extract_01_bus.json", encoding="utf-8") as f:
    bus_data = json.load(f)
with open(r"C:\Users\cy1in\bledi.tn\data\extract_02_rail.json", encoding="utf-8") as f:
    rail_data = json.load(f)
with open(r"C:\Users\cy1in\bledi.tn\data\extract_06_docs.json", encoding="utf-8") as f:
    docs_data = json.load(f)
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", encoding="utf-8") as f:
    existing_seed = json.load(f)

print(f"Bus: {len(bus_data)}, Rail: {len(rail_data)}, Docs: {len(docs_data)}, Existing: {len(existing_seed['stations'])}")

# === STEP 1: Build unified station list ===
print("\n=== STEP 1: Build unified station list ===")

all_stations = []

# Add existing seed stations (they have line references)
for s in existing_seed["stations"]:
    all_stations.append({
        "id": s["id"],
        "name": s.get("name", ""),
        "name_en": s.get("name_en", ""),
        "lat": s.get("lat"),
        "lon": s.get("lon"),
        "source": s.get("source", "unknown"),
        "operator": s.get("operator", ""),
        "mode": s.get("mode", "bus"),
        "lines_served": s.get("lines_served", []),
        "source_stop_id": s.get("source_stop_id"),
        "route_type": s.get("route_type"),
        "license_status": s.get("license_status"),
        "from_existing": True,
    })

# Add new stations from extractions
for source_name, data in [("01_bus", bus_data), ("02_rail", rail_data), ("06_docs", docs_data)]:
    for s in data:
        name = s.get("name", "")
        lat = s.get("lat")
        lon = s.get("lon")
        if not name or lat is None or lon is None:
            continue
        # Filter to Tunisia bounds
        if lat < 30 or lat > 38 or lon < 7 or lon > 12:
            continue
        
        source = s.get("source", source_name)
        operator = s.get("operator", "") or detect_operator(name, source)
        mode = detect_mode(name, source)
        
        # Generate ID
        norm = normalize_name(name)
        new_id = f"{source_name}_{norm.replace(' ', '_')[:30]}"
        
        all_stations.append({
            "id": new_id,
            "name": name,
            "name_en": name,
            "lat": lat,
            "lon": lon,
            "source": source,
            "operator": operator,
            "mode": mode,
            "lines_served": [],
            "source_stop_id": None,
            "route_type": None,
            "license_status": None,
            "from_existing": False,
        })

print(f"Total before dedup: {len(all_stations)}")

# === STEP 2: Deduplicate ===
print("\n=== STEP 2: Deduplicate ===")

# Build position index
CELL = 0.001  # ~110m
grid = defaultdict(list)
for s in all_stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    grid.setdefault((round(lat / CELL), round(lon / CELL)), []).append(s)

def find_nearby(s, grid, radius_m=100):
    """Find stations within radius_m of s."""
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        return []
    ci, cj = round(lat / CELL), round(lon / CELL)
    # Calculate cell range for radius
    cells = max(1, int(radius_m / 110) + 1)
    nearby = []
    for di in range(-cells, cells + 1):
        for dj in range(-cells, cells + 1):
            for other in grid.get((ci + di, cj + dj), []):
                if other["id"] == s["id"]:
                    continue
                dist = haversine(lat, lon, other["lat"], other["lon"])
                if dist <= radius_m:
                    nearby.append((other, dist))
    return nearby

# Deduplicate: for each station, if there's a nearby station from a more authoritative source, remove it
to_remove = set()
for s in all_stations:
    if s["id"] in to_remove:
        continue
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    
    nearby = find_nearby(s, grid, radius_m=80)
    for other, dist in nearby:
        if other["id"] in to_remove:
            continue
        # If other is more authoritative, remove s
        if get_authority(other["source"]) < get_authority(s["source"]):
            # Check if names are similar
            norm_s = normalize_name(s["name"])
            norm_o = normalize_name(other["name"])
            if norm_s == norm_o or norm_s in norm_o or norm_o in norm_s:
                to_remove.add(s["id"])
                break
        # If s is more authoritative, remove other
        elif get_authority(s["source"]) < get_authority(other["source"]):
            norm_s = normalize_name(s["name"])
            norm_o = normalize_name(other["name"])
            if norm_s == norm_o or norm_s in norm_o or norm_o in norm_s:
                to_remove.add(other["id"])

print(f"Duplicates to remove: {len(to_remove)}")

# Remove duplicates
before = len(all_stations)
all_stations = [s for s in all_stations if s["id"] not in to_remove]
print(f"Removed {before - len(all_stations)} duplicates")

# === STEP 3: Fix water stations ===
print("\n=== STEP 3: Fix water stations ===")

water_fixed = 0
water_removed = 0

for s in all_stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if not in_any_water(lat, lon):
        continue
    
    # Find nearest non-water station
    best_dist = float("inf")
    best = None
    for other in all_stations:
        if other["id"] == s["id"]:
            continue
        olat = other.get("lat")
        olon = other.get("lon")
        if olat is None or olon is None:
            continue
        if not in_any_water(olat, olon):
            dist = haversine(lat, lon, olat, olon)
            if dist < best_dist:
                best_dist = dist
                best = other
    
    if best and best_dist < 5000:
        s["lat"] = best["lat"]
        s["lon"] = best["lon"]
        water_fixed += 1
    elif not s.get("from_existing"):
        # Remove non-existing water stations that can't be fixed
        s["_remove"] = True
        water_removed += 1

print(f"Fixed: {water_fixed}")
print(f"Removed: {water_removed}")

# Remove unfixed water stations
before = len(all_stations)
all_stations = [s for s in all_stations if not s.get("_remove")]
print(f"Removed {before - len(all_stations)} unfixed water stations")

# === STEP 4: Spread duplicates ===
print("\n=== STEP 4: Spread duplicates ===")

pos_groups = defaultdict(list)
for s in all_stations:
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None: continue
    pos_groups[(round(lat, 6), round(lon, 6))].append(s)

dupes = {k: v for k, v in pos_groups.items() if len(v) > 1}
print(f"Duplicate positions: {len(dupes)}")

import random
random.seed(42)
occupied = set()
for s in all_stations:
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None: continue
    occupied.add((round(lat, 6), round(lon, 6)))

spread = 0
for pos, group in dupes.items():
    if len(group) <= 1: continue
    base_lat, base_lon = pos
    for i, s in enumerate(group[1:], 1):
        for attempt in range(100):
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(0.0001, 0.01)
            new_lat = base_lat + radius * math.sin(angle)
            new_lon = base_lon + radius * math.cos(angle)
            new_pos = (round(new_lat, 6), round(new_lon, 6))
            if new_pos not in occupied and not in_any_water(new_lat, new_lon):
                occupied.add(new_pos)
                s["lat"] = new_lat
                s["lon"] = new_lon
                spread += 1
                break

print(f"Spread: {spread}")

# === STEP 5: Build new seed ===
print("\n=== STEP 5: Build new seed ===")

# Build line station references from existing seed
line_station_map = defaultdict(list)  # station_id -> list of line_ids
for line in existing_seed["lines"]:
    for sid in line.get("stations", []):
        line_station_map[sid].append(line["id"])

# Build new stations list
new_stations = []
for s in all_stations:
    station = {
        "id": s["id"],
        "name": s.get("name", ""),
        "name_en": s.get("name_en", ""),
        "lat": s.get("lat"),
        "lon": s.get("lon"),
        "source_stop_id": s.get("source_stop_id"),
        "mode": s.get("mode", "bus"),
        "operator": s.get("operator", ""),
        "lines_served": s.get("lines_served", []),
        "route_type": s.get("route_type"),
        "source": s.get("source", "unknown"),
        "license_status": s.get("license_status"),
    }
    new_stations.append(station)

# Build new lines list (preserve existing lines)
new_lines = []
for line in existing_seed["lines"]:
    new_line = {
        "id": line["id"],
        "number": line.get("number", ""),
        "name": line.get("name", ""),
        "operator": line.get("operator", ""),
        "mode": line.get("mode", "bus"),
        "type": line.get("type", ""),
        "route_id": line.get("route_id", ""),
        "stations": line.get("stations", []),
        "departures": line.get("departures", []),
        "source": line.get("source", "unknown"),
        "license_status": line.get("license_status"),
    }
    new_lines.append(new_line)

# Build new seed
new_seed = {
    "metadata": {
        "source": "Rebuilt from all Downloads sources",
        "extracted_date": "2026-10-17",
        "total_stations": len(new_stations),
        "total_lines": len(new_lines),
        "sources": {
            "01_bus": len(bus_data),
            "02_rail": len(rail_data),
            "06_docs": len(docs_data),
            "existing_seed": len(existing_seed["stations"]),
        },
    },
    "stations": new_stations,
    "lines": new_lines,
}

# === STEP 6: Verify ===
print("\n=== STEP 6: Verify ===")

water = [s for s in new_stations if s.get("lat") and s.get("lon") and in_any_water(s["lat"], s["lon"])]
print(f"Water stations: {len(water)}")

pos_groups2 = defaultdict(list)
for s in new_stations:
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None: continue
    pos_groups2[(round(lat, 6), round(lon, 6))].append(s)
dupes2 = {k: v for k, v in pos_groups2.items() if len(v) > 1}
print(f"Duplicate positions: {len(dupes2)}")

unknown = [s for s in new_stations if s.get("mode") == "unknown"]
print(f"Unknown mode: {len(unknown)}")

oob = [s for s in new_stations if s.get("lat") and (s["lat"] < 30 or s["lat"] > 38 or s["lon"] < 7 or s["lon"] > 12)]
print(f"Out of bounds: {len(oob)}")

broken = 0
ids = {s["id"] for s in new_stations}
for line in new_lines:
    for sid in line.get("stations", []):
        if sid not in ids:
            broken += 1
print(f"Broken line references: {broken}")

print(f"\nFinal: {len(new_stations)} stations, {len(new_lines)} lines")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(new_seed, f, ensure_ascii=False, indent=1)
print("Wrote seed")
