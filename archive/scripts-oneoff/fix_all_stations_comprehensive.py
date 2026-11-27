"""Comprehensive station fix:
1. Spread duplicate positions to unique locations
2. Fix remaining water stations
3. Handle unknown-mode stations
"""
import json
import math
import random

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

# Water polygons
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

# === STEP 1: Fix remaining water stations ===
print("\n=== STEP 1: Fix remaining water stations ===")
water_fixed = 0
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if in_any_water(lat, lon):
        # Find nearest land station
        best_dist = float("inf")
        best_lat, best_lon = lat, lon
        for ls in stations:
            if ls["id"] == s["id"]:
                continue
            llat = ls.get("lat")
            llon = ls.get("lon")
            if llat is None or llon is None:
                continue
            if not in_any_water(llat, llon):
                dist = haversine(lat, lon, llat, llon)
                if dist < best_dist:
                    best_dist = dist
                    best_lat, best_lon = llat, llon
        if best_dist < 10000:
            s["lat"] = best_lat
            s["lon"] = best_lon
            water_fixed += 1

print(f"Fixed {water_fixed} water stations")

# === STEP 2: Spread duplicate positions ===
print("\n=== STEP 2: Spread duplicate positions ===")

# Group stations by position
from collections import defaultdict
pos_groups = defaultdict(list)
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    pos_key = (round(lat, 4), round(lon, 4))
    pos_groups[pos_key].append(s)

# Find duplicates
duplicates = {k: v for k, v in pos_groups.items() if len(v) > 1}
print(f"Duplicate positions: {len(duplicates)}")
total_dupes = sum(len(v) for v in duplicates.values())
print(f"Total stations at duplicate positions: {total_dupes}")

# Spread duplicates in a small circle
spread_count = 0
for pos, group in duplicates.items():
    if len(group) <= 1:
        continue
    
    # Keep first station at original position
    # Spread others in a circle around it
    base_lat, base_lon = pos
    radius = 0.001  # ~100m
    
    for i, s in enumerate(group[1:], 1):
        angle = (2 * math.pi * i) / (len(group) - 1) if len(group) > 1 else 0
        new_lat = base_lat + radius * math.sin(angle)
        new_lon = base_lon + radius * math.cos(angle)
        
        # Make sure new position is not in water
        if not in_any_water(new_lat, new_lon):
            s["lat"] = round(new_lat, 6)
            s["lon"] = round(new_lon, 6)
            spread_count += 1
        else:
            # Try a smaller radius
            for r in [0.0005, 0.0002]:
                new_lat = base_lat + r * math.sin(angle)
                new_lon = base_lon + r * math.cos(angle)
                if not in_any_water(new_lat, new_lon):
                    s["lat"] = round(new_lat, 6)
                    s["lon"] = round(new_lon, 6)
                    spread_count += 1
                    break

print(f"Spread {spread_count} stations to unique positions")

# === STEP 3: Handle unknown-mode stations ===
print("\n=== STEP 3: Handle unknown-mode stations ===")
mode_fixed = 0
for s in stations:
    if s.get("mode") == "unknown":
        # Try to infer from lines_served (list of dicts)
        lines = s.get("lines_served", [])
        if lines:
            first_line = lines[0]
            if isinstance(first_line, dict):
                line_id = str(first_line.get("id", "")).lower()
            else:
                line_id = str(first_line).lower()
            if "bus" in line_id:
                s["mode"] = "bus"
            elif "train" in line_id or "rail" in line_id:
                s["mode"] = "train"
            elif "metro" in line_id:
                s["mode"] = "metro"
            elif "louage" in line_id or "louaj" in line_id:
                s["mode"] = "louaj"
            else:
                s["mode"] = "bus"
            mode_fixed += 1
        else:
            s["mode"] = "bus"
            mode_fixed += 1

print(f"Fixed {mode_fixed} unknown-mode stations")

# === VERIFY ===
print("\n=== VERIFICATION ===")

# Check water stations
water_remaining = []
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    if in_any_water(lat, lon):
        water_remaining.append(s)
print(f"Water stations remaining: {len(water_remaining)}")

# Check duplicates
pos_groups2 = defaultdict(list)
for s in stations:
    lat = s.get("lat")
    lon = s.get("lon")
    if lat is None or lon is None:
        continue
    pos_key = (round(lat, 4), round(lon, 4))
    pos_groups2[pos_key].append(s)
duplicates2 = {k: v for k, v in pos_groups2.items() if len(v) > 1}
print(f"Duplicate positions remaining: {len(duplicates2)}")

# Check unknown mode
unknown_mode = [s for s in stations if s.get("mode") == "unknown"]
print(f"Unknown mode stations: {len(unknown_mode)}")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)

print(f"\nWrote seed with {len(stations)} stations")
