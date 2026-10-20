"""Careful station reorganization:
1. Fix water stations using reference DB coordinates
2. Only remove duplicates that are NOT referenced by any line
3. Preserve all line references
4. Keep the most authoritative version of each station
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
    name = re.sub(r'^(gare|station|arrêt|stop|halte)\s+', '', name)
    name = re.sub(r'\s+(gare|station|arrêt|stop|halte)$', '', name)
    name = re.sub(r'[^\w\s]', '', name)
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

# Load data
print("Loading data...")
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)
with open(r"C:\Users\cy1in\bledi.tn\data\station_reference.json") as f:
    reference = json.load(f)

stations = seed["stations"]
lines = seed["lines"]
print(f"Original seed: {len(stations)} stations, {len(lines)} lines")

# Build reference lookup by normalized name
ref_by_name = {}
for ref in reference.get("stations", []):
    name = normalize_name(ref.get("name", ""))
    if name:
        ref_by_name[name] = ref

# Build set of station IDs referenced by lines
referenced_ids = set()
for line in lines:
    for sid in line.get("stations", []):
        referenced_ids.add(sid)
print(f"Stations referenced by lines: {len(referenced_ids)}")

# === STEP 1: Fix water stations ===
print("\n=== STEP 1: Fix water stations ===")
water_fixed = 0
water_removed = 0

for s in stations:
    sid = s["id"]
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    
    if not in_any_water(lat, lon):
        continue
    
    # This station is in water - find correct coordinates
    name = s.get("name", "")
    norm_name = normalize_name(name)
    
    # Try to find in reference DB
    found = False
    if norm_name in ref_by_name:
        ref = ref_by_name[norm_name]
        ref_lat = ref.get("lat")
        ref_lon = ref.get("lon")
        if ref_lat and ref_lon and not in_any_water(ref_lat, ref_lon):
            s["lat"] = ref_lat
            s["lon"] = ref_lon
            water_fixed += 1
            found = True
    
    if not found:
        # Try fuzzy name matching
        for ref_name, ref in ref_by_name.items():
            if len(norm_name) > 3 and len(ref_name) > 3:
                if norm_name in ref_name or ref_name in norm_name:
                    ref_lat = ref.get("lat")
                    ref_lon = ref.get("lon")
                    if ref_lat and ref_lon and not in_any_water(ref_lat, ref_lon):
                        s["lat"] = ref_lat
                        s["lon"] = ref_lon
                        water_fixed += 1
                        found = True
                        break
    
    if not found:
        # Remove station ONLY if not referenced by any line
        if sid not in referenced_ids:
            s["_remove"] = True
            water_removed += 1
        else:
            # Keep referenced stations even if we can't fix them
            # Try moving to nearest non-water position
            best_dist = float("inf")
            best_lat, best_lon = lat, lon
            for other in stations:
                if other["id"] == sid:
                    continue
                olat = other.get("lat")
                olon = other.get("lon")
                if olat is None or olon is None:
                    continue
                if not in_any_water(olat, olon):
                    dist = haversine(lat, lon, olat, olon)
                    if dist < best_dist:
                        best_dist = dist
                        best_lat, best_lon = olat, olon
            if best_dist < 5000:
                s["lat"] = best_lat
                s["lon"] = best_lon
                water_fixed += 1
            else:
                # Can't fix, but keep it (referenced by line)
                pass

print(f"Fixed: {water_fixed}")
print(f"Removed (not referenced): {water_removed}")

# Remove unfixed water stations
before = len(stations)
seed["stations"] = [s for s in stations if not s.get("_remove")]
print(f"Removed {before - len(seed['stations'])} stations")

# === STEP 2: Remove duplicates (only non-referenced) ===
print("\n=== STEP 2: Remove duplicates ===")

# Build proximity index
CELL = 0.002
grid = defaultdict(list)
for s in seed["stations"]:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    grid.setdefault((round(lat / CELL), round(lon / CELL)), []).append(s)

def find_duplicates(s, grid, tolerance_m=150):
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        return []
    ci, cj = round(lat / CELL), round(lon / CELL)
    duplicates = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for other in grid.get((ci + di, cj + dj), []):
                if other["id"] == s["id"]:
                    continue
                dist = haversine(lat, lon, other["lat"], other["lon"])
                if dist <= tolerance_m:
                    duplicates.append((other, dist))
    return duplicates

AUTHORITY = {
    "downloads:SNTRI stops": 1,
    "downloads:GTFS Horaires des bus de la SORETRAK - ": 1,
    "downloads:GTFS Horaires des voyages de la société": 1,
    "downloads:GTFS Horaires des voyages de la TRANSTU": 1,
    "downloads:SNCFT Banlieue Sahel stations": 1,
    "downloads:SNCFT Banlieue Sud stations": 1,
    "official-public": 2,
    "official-open-data": 2,
    "downloads-transport-export": 2,
    "downloads:BLEDI curated workbook": 2,
    "downloads:TNRP national bus-stop registry": 3,
    "tunismapper": 4,
    "google-places-workbook": 5,
    "tunisia_louage_network.csv": 6,
    "unknown": 7,
}

def get_authority(s):
    return AUTHORITY.get(s.get("source", ""), 8)

# Find duplicates - only remove if NOT referenced by any line
duplicates_removed = 0
to_remove = set()

for s in seed["stations"]:
    if s["id"] in to_remove:
        continue
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    
    dups = find_duplicates(s, grid)
    for other, dist in dups:
        if other["id"] in to_remove:
            continue
        # Only remove if NOT referenced by any line
        if other["id"] not in referenced_ids:
            # Keep the more authoritative one
            if get_authority(s) <= get_authority(other):
                to_remove.add(other["id"])
            else:
                to_remove.add(s["id"])
                break

print(f"Duplicates found: {len(to_remove)}")

# Remove duplicates
before = len(seed["stations"])
seed["stations"] = [s for s in seed["stations"] if s["id"] not in to_remove]
print(f"Removed {before - len(seed['stations'])} duplicates")

# === STEP 3: Fix unknown modes ===
print("\n=== STEP 3: Fix unknown modes ===")
mode_fixed = 0
for s in seed["stations"]:
    if s.get("mode") == "unknown":
        s["mode"] = "bus"
        mode_fixed += 1
print(f"Fixed {mode_fixed} unknown modes")

# === STEP 4: Final verification ===
print("\n=== STEP 4: Final verification ===")

water_remaining = [s for s in seed["stations"] if s.get("lat") and s.get("lon") and in_any_water(s["lat"], s["lon"])]
print(f"Water stations: {len(water_remaining)}")

pos_groups = defaultdict(list)
for s in seed["stations"]:
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None: continue
    pos_groups[(round(lat, 6), round(lon, 6))].append(s)
dupes = {k: v for k, v in pos_groups.items() if len(v) > 1}
print(f"Duplicate positions: {len(dupes)}")

unknown = [s for s in seed["stations"] if s.get("mode") == "unknown"]
print(f"Unknown mode: {len(unknown)}")

oob = [s for s in seed["stations"] if s.get("lat") and (s["lat"] < 30 or s["lat"] > 37.6 or s["lon"] < 7 or s["lon"] > 11.7)]
print(f"Out of bounds: {len(oob)}")

# Check line references
broken_refs = 0
station_ids = {s["id"] for s in seed["stations"]}
for line in lines:
    for sid in line.get("stations", []):
        if sid not in station_ids:
            broken_refs += 1
print(f"Broken line references: {broken_refs}")

print(f"\nFinal: {len(seed['stations'])} stations")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)
print("Wrote seed")
