"""Rebuild seed from scratch with strict coordinate validation.

Strategy:
1. Load all extract data and existing seed
2. Load water_stations.json to identify known water stations
3. Filter out ALL stations that are:
   a. In water_stations.json (known water stations)
   b. In the Gulf of Tunis water area (simple polygon check)
   c. In the Lake of Tunis water area
   d. In the Bizerte Lagoon water area
4. Deduplicate by name + position
5. Write clean seed file
"""
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
import json
import math
import re
from collections import defaultdict, Counter

TUNISIA_BOUNDS = {'lat_min': 30.0, 'lat_max': 38.0, 'lon_min': 7.0, 'lon_max': 12.0}

# Gulf of Tunis water polygon (precise - only the sea, not the coast)
# The coast runs roughly along lon 10.28-10.30, sea is north/east
GULF_TUNIS_WATER = [
    (36.87, 10.28), (36.90, 10.30), (36.92, 10.32), (36.95, 10.35),
    (36.98, 10.38), (37.00, 10.40), (37.00, 10.50), (36.98, 10.55),
    (36.95, 10.50), (36.90, 10.45), (36.87, 10.40), (36.85, 10.35),
    (36.85, 10.30), (36.87, 10.28)
]

# Lake of Tunis / Sebkha (precise)
LAKE_TUNIS_WATER = [
    (36.78, 10.12), (36.80, 10.15), (36.82, 10.18), (36.85, 10.20),
    (36.85, 10.22), (36.82, 10.22), (36.80, 10.20), (36.78, 10.18),
    (36.75, 10.15), (36.72, 10.12), (36.75, 10.10), (36.78, 10.12)
]

# Bizerte Lagoon (precise)
BIZERTE_LAGOON_WATER = [
    (37.18, 9.82), (37.22, 9.80), (37.25, 9.82), (37.28, 9.85),
    (37.30, 9.88), (37.32, 9.92), (37.35, 9.95), (37.38, 9.98),
    (37.40, 10.00), (37.38, 10.02), (37.35, 10.00), (37.32, 9.98),
    (37.28, 9.95), (37.25, 9.92), (37.22, 9.90), (37.18, 9.88),
    (37.18, 9.82)
]


def point_in_polygon(lat, lon, poly):
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][1], poly[i][0]
        xj, yj = poly[j][1], poly[j][0]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'^(gare|station|arrêt|stop|halte|محطة|gare de)\s+', '', name)
    name = re.sub(r'\s+(gare|station|arrêt|stop|halte)$', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = ' '.join(name.split())
    return name


def is_valid_coordinate(lat, lon):
    if lat is None or lon is None:
        return False
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    if lat == 0 and lon == 0:
        return False
    if lat < TUNISIA_BOUNDS['lat_min'] or lat > TUNISIA_BOUNDS['lat_max']:
        return False
    if lon < TUNISIA_BOUNDS['lon_min'] or lon > TUNISIA_BOUNDS['lon_max']:
        return False
    return True


def in_water(lat, lon):
    """Check if coordinates are in a known water body."""
    if point_in_polygon(lat, lon, GULF_TUNIS_WATER):
        return True
    if point_in_polygon(lat, lon, LAKE_TUNIS_WATER):
        return True
    if point_in_polygon(lat, lon, BIZERTE_LAGOON_WATER):
        return True
    return False


def load_data():
    data_dir = REPO / "data"
    with open(f"{data_dir}\\extract_01_bus.json", encoding="utf-8") as f:
        bus_data = json.load(f)
    with open(f"{data_dir}\\extract_02_rail.json", encoding="utf-8") as f:
        rail_data = json.load(f)
    with open(f"{data_dir}\\extract_06_docs.json", encoding="utf-8") as f:
        docs_data = json.load(f)
    with open(f"{data_dir}\\seed_all_tunisia_routes.tagged.json", encoding="utf-8") as f:
        existing_seed = json.load(f)
    return bus_data, rail_data, docs_data, existing_seed


def load_water_stations():
    """Load known water station IDs from water_stations.json."""
    import os
    water_path = REPO / "data" / "water_stations.json"
    if not os.path.exists(water_path):
        return set()
    try:
        with open(water_path, encoding="utf-8") as f:
            data = json.load(f)
        return {s["id"] for s in data.get("water_stations", [])}
    except:
        return set()


def main():
    print("Loading data...")
    bus_data, rail_data, docs_data, existing_seed = load_data()
    water_station_ids = load_water_stations()
    
    print(f"  Bus: {len(bus_data)}")
    print(f"  Rail: {len(rail_data)}")
    print(f"  Docs: {len(docs_data)}")
    print(f"  Existing seed stations: {len(existing_seed['stations'])}")
    print(f"  Known water station IDs: {len(water_station_ids)}")
    
    # === STEP 1: Collect ALL stations, filter out water ===
    print("\n=== STEP 1: Collect stations (filtering water) ===")
    
    all_stations = []
    water_filtered = 0
    water_id_filtered = 0
    
    # Add from extracts
    for source_name, data in [("01_bus", bus_data), ("02_rail", rail_data), ("06_docs", docs_data)]:
        for s in data:
            name = s.get("name", "")
            lat = s.get("lat")
            lon = s.get("lon")
            if not name or not is_valid_coordinate(lat, lon):
                continue
            
            # Check if this station ID is in the known water list
            sid = s.get("id", "")
            if sid in water_station_ids:
                water_id_filtered += 1
                continue
            
            # Check if coordinates are in water
            if in_water(lat, lon):
                water_filtered += 1
                continue
            
            norm = normalize_name(name)
            if not norm:
                continue
            
            all_stations.append({
                "name": name,
                "lat": lat,
                "lon": lon,
                "source": source_name,
                "original_source": s.get("source", ""),
                "operator": s.get("operator", ""),
                "mode": s.get("mode", "bus"),
            })
    
    # Add from existing seed (these have line references)
    for s in existing_seed["stations"]:
        name = s.get("name", "")
        lat = s.get("lat")
        lon = s.get("lon")
        if not name or not is_valid_coordinate(lat, lon):
            continue
        
        # Check if this station ID is in the known water list
        sid = s.get("id", "")
        if sid in water_station_ids:
            water_id_filtered += 1
            continue
        
        # Check if coordinates are in water
        if in_water(lat, lon):
            water_filtered += 1
            continue
        
        norm = normalize_name(name)
        if not norm:
            continue
        
        all_stations.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "source": "existing_seed",
            "original_source": s.get("source", ""),
            "operator": s.get("operator", ""),
            "mode": s.get("mode", "bus"),
            "lines_served": s.get("lines_served", []),
            "route_type": s.get("route_type"),
            "license_status": s.get("license_status"),
        })
    
    print(f"  Total collected: {len(all_stations)}")
    print(f"  Water filtered (polygon): {water_filtered}")
    print(f"  Water filtered (ID): {water_id_filtered}")
    
    # === STEP 2: Group by normalized name ===
    print("\n=== STEP 2: Group by name ===")
    
    name_groups = defaultdict(list)
    for s in all_stations:
        norm = normalize_name(s["name"])
        name_groups[norm].append(s)
    
    print(f"  Unique names: {len(name_groups)}")
    
    # === STEP 3: For each name group, pick the best coordinate ===
    print("\n=== STEP 3: Pick best coordinate per name ===")
    
    validated_stations = []
    multi_coord_names = 0
    
    for norm_name, entries in name_groups.items():
        if len(entries) == 1:
            validated_stations.append(entries[0])
            continue
        
        # Multiple entries with same name - pick the best one
        multi_coord_names += 1
        
        # Strategy: pick the entry with the most line references,
        # then the one that is most central (lowest total distance to others)
        
        # First, prefer entries with line references
        with_lines = [e for e in entries if e.get("lines_served")]
        
        if with_lines:
            # Pick the one with the most line references
            best = max(with_lines, key=lambda e: len(e.get("lines_served", [])))
        else:
            # No line references - pick the most central one
            best = None
            best_total_dist = float("inf")
            for e in entries:
                total_dist = sum(haversine(e["lat"], e["lon"], o["lat"], o["lon"]) for o in entries)
                if total_dist < best_total_dist:
                    best_total_dist = total_dist
                    best = e
        
        validated_stations.append(best)
    
    print(f"  Names with multiple entries: {multi_coord_names}")
    print(f"  After name dedup: {len(validated_stations)}")
    
    # === STEP 4: Deduplicate by position (within 150m) ===
    print("\n=== STEP 4: Deduplicate by position ===")
    
    CELL = 0.002  # ~220m
    grid = defaultdict(list)
    for s in validated_stations:
        key = (round(s["lat"] / CELL), round(s["lon"] / CELL))
        grid[key].append(s)
    
    deduped = []
    for key, group in grid.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        
        # Multiple stations in same cell - merge them
        best = max(group, key=lambda s: (len(s.get("lines_served", [])), s["name"]))
        
        # Merge line references from all stations in the group
        merged_lines = []
        for s in group:
            for line in s.get("lines_served", []):
                if line not in merged_lines:
                    merged_lines.append(line)
        
        best["lines_served"] = merged_lines
        deduped.append(best)
    
    print(f"  Before: {len(validated_stations)}")
    print(f"  After: {len(deduped)}")
    print(f"  Removed: {len(validated_stations) - len(deduped)}")
    
    validated_stations = deduped
    
    # === STEP 5: Final verification ===
    print("\n=== STEP 5: Final verification ===")
    
    water_remaining = [s for s in validated_stations if in_water(s["lat"], s["lon"])]
    print(f"  Water stations remaining: {len(water_remaining)}")
    if water_remaining:
        for s in water_remaining[:20]:
            print(f"    {s['name']} ({s['lat']:.4f}, {s['lon']:.4f})")
    
    # Check for duplicate positions
    pos_groups = defaultdict(list)
    for s in validated_stations:
        key = (round(s["lat"], 6), round(s["lon"], 6))
        pos_groups[key].append(s)
    dupes = {k: v for k, v in pos_groups.items() if len(v) > 1}
    print(f"  Duplicate positions: {len(dupes)}")
    
    # Count by mode
    modes = {}
    for s in validated_stations:
        mode = s.get("mode", "unknown")
        modes[mode] = modes.get(mode, 0) + 1
    print(f"  Modes: {modes}")
    
    # === STEP 6: Build final seed ===
    print("\n=== STEP 6: Build final seed ===")
    
    # Build lines list (preserve from existing seed)
    new_lines = []
    for line in existing_seed.get("lines", []):
        new_lines.append({
            "id": line.get("id", ""),
            "number": line.get("number", ""),
            "name": line.get("name", ""),
            "operator": line.get("operator", ""),
            "mode": line.get("mode", "bus"),
            "type": line.get("type", ""),
            "route_id": line.get("route_id", ""),
            "stations": line.get("stations", []),
            "departures": line.get("departures", []),
            "source": line.get("source", ""),
            "license_status": line.get("license_status", ""),
        })
    
    # Build stations list
    new_stations = []
    for s in validated_stations:
        mode = s.get("mode", "bus")
        safe_name = re.sub(r'[^\w]', '_', normalize_name(s["name"]))[:40]
        station_id = f"{s['source']}_{safe_name}"
        
        new_stations.append({
            "id": station_id,
            "name": s["name"],
            "name_en": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "mode": mode,
            "operator": s.get("operator", ""),
            "lines_served": s.get("lines_served", []),
            "route_type": s.get("route_type"),
            "license_status": s.get("license_status"),
            "source": s.get("original_source", s["source"]),
        })
    
    # Build metadata
    metadata = {
        "source": "Rebuilt from all Downloads sources with strict coordinate validation",
        "extracted_date": "2026-10-17",
        "total_stations": len(new_stations),
        "total_lines": len(new_lines),
        "sources": {
            "01_bus": len(bus_data),
            "02_rail": len(rail_data),
            "06_docs": len(docs_data),
            "existing_seed": len(existing_seed["stations"]),
        },
        "validation": {
            "water_filtered_polygon": water_filtered,
            "water_filtered_id": water_id_filtered,
            "name_deduped": multi_coord_names,
            "position_deduped": len(validated_stations) - len(deduped),
        }
    }
    
    new_seed = {
        "metadata": metadata,
        "stations": new_stations,
        "lines": new_lines,
    }
    
    print(f"\n  Final: {len(new_stations)} stations, {len(new_lines)} lines")
    
    # Write
    output_path = REPO / "data" / "seed_all_tunisia_routes.tagged.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(new_seed, f, ensure_ascii=False, indent=1)
    print(f"\n  Wrote {output_path}")
    
    return len(new_stations), len(new_lines)


if __name__ == "__main__":
    main()
