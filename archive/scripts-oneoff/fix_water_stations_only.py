"""Minimal station fix: only fix water stations, preserve everything else.
Uses reference DB to find correct coordinates for water stations.
Does NOT remove any stations or touch line references.
"""
import json
import math
import re

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
print(f"Original seed: {len(stations)} stations")

# Build reference lookup by normalized name
ref_by_name = {}
for ref in reference.get("stations", []):
    name = normalize_name(ref.get("name", ""))
    if name:
        ref_by_name[name] = ref

# === FIX WATER STATIONS ===
print("\n=== Fixing water stations ===")
water_fixed = 0
water_unfixed = 0

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
    
    # Try exact name match in reference DB
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
        water_unfixed += 1

print(f"Fixed: {water_fixed}")
print(f"Unfixed (no reference match): {water_unfixed}")

# === VERIFY ===
print("\n=== Verification ===")

water_remaining = [s for s in stations if s.get("lat") and s.get("lon") and in_any_water(s["lat"], s["lon"])]
print(f"Water stations remaining: {len(water_remaining)}")

# Check line references
broken_refs = 0
station_ids = {s["id"] for s in stations}
for line in seed["lines"]:
    for sid in line.get("stations", []):
        if sid not in station_ids:
            broken_refs += 1
print(f"Broken line references: {broken_refs}")

print(f"\nFinal: {len(stations)} stations")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)
print("Wrote seed")
