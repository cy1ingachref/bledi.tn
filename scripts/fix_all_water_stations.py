"""Fix ALL stations in water by finding nearest land station.
For each water station:
1. Find nearest land station (any distance)
2. Move water station to that location
3. Only remove if no land station exists within 10km
"""
import json
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

GULF_TUNIS = [
    (36.85, 10.00), (36.90, 10.10), (36.95, 10.20), (37.00, 10.30),
    (37.05, 10.40), (37.00, 10.50), (36.90, 10.40), (36.85, 10.30),
    (36.85, 10.00),
]
LAKE_TUNIS = [
    (36.75, 10.10), (36.80, 10.15), (36.85, 10.20), (36.80, 10.25),
    (36.75, 10.20), (36.70, 10.15), (36.75, 10.10),
]
BIZERTE_LAGOON = [
    (37.15, 9.85), (37.20, 9.80), (37.25, 9.85), (37.30, 9.90),
    (37.35, 9.95), (37.30, 10.00), (37.25, 9.95), (37.20, 9.90),
    (37.15, 9.85),
]

def point_in_polygon(lat, lon, polygon):
    n = len(polygon)
    inside = False
    for i in range(n):
        p1_lat, p1_lon = polygon[i]
        p2_lat, p2_lon = polygon[(i + 1) % n]
        if (p1_lon > lon) != (p2_lon > lon):
            t = (lon - p1_lon) / (p2_lon - p1_lon)
            intersect_lat = p1_lat + t * (p2_lat - p1_lat)
            if lat < intersect_lat:
                inside = not inside
    return inside

def in_any_water(lat, lon):
    return (point_in_polygon(lat, lon, GULF_TUNIS) or
            point_in_polygon(lat, lon, LAKE_TUNIS) or
            point_in_polygon(lat, lon, BIZERTE_LAGOON))

# Load seed
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)

stations = seed["stations"]
print(f"Total stations: {len(stations)}")

# Build land station index
land_stations = []
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if not in_any_water(lat, lon):
        land_stations.append(s)

print(f"Land stations: {len(land_stations)}")

# Find water stations
water_stations = []
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if in_any_water(lat, lon):
        water_stations.append(s)

print(f"Water stations: {len(water_stations)}")

# Fix each water station
fixed = 0
removed = 0

for s in water_stations:
    sid = s["id"]
    name = s.get("name", "")
    lat = s.get("lat", 0)
    lon = s.get("lon", 0)
    
    # Find nearest land station
    best_dist = float("inf")
    best_station = None
    
    for ls in land_stations:
        if ls["id"] == sid:
            continue
        llat = ls.get("lat", 0)
        llon = ls.get("lon", 0)
        dist = haversine(lat, lon, llat, llon)
        if dist < best_dist:
            best_dist = dist
            best_station = ls
    
    if best_station and best_dist < 10000:  # Within 10km
        old_lat, old_lon = s["lat"], s["lon"]
        s["lat"] = best_station["lat"]
        s["lon"] = best_station["lon"]
        fixed += 1
        if fixed <= 10:
            print(f"  Fixed {sid} ({name[:20]}): ({old_lat:.4f}, {old_lon:.4f}) -> ({s['lat']:.4f}, {s['lon']:.4f}) [dist={best_dist:.0f}m]")
    else:
        s["_remove"] = True
        removed += 1
        if removed <= 10:
            print(f"  REMOVE {sid} ({name[:20]}): no land station within 10km")

print(f"\nFixed: {fixed}")
print(f"Removed: {removed}")

# Remove unfixed
before = len(stations)
seed["stations"] = [s for s in stations if not s.get("_remove")]
removed_count = before - len(seed["stations"])
print(f"Removed {removed_count} stations")

# Verify
remaining_water = []
for s in seed["stations"]:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if in_any_water(lat, lon):
        remaining_water.append(s)

print(f"\nRemaining water stations: {len(remaining_water)}")
for s in remaining_water[:10]:
    print(f"  {s['id']:40} {s.get('name','?')[:30]:32} ({s['lat']:.4f}, {s['lon']:.4f}) {s.get('source','?')}")

bc_count = len([s for s in seed["stations"] if s.get("source") == "bizerteconnect-api"])
print(f"\nFinal: {len(seed['stations'])} stations, {bc_count} BizerteConnect")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)

print(f"Wrote seed")
