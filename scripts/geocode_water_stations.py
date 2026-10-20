"""Geocode remaining water stations using Nominatim."""
import json
import time
import urllib.request
import urllib.parse
import re

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

def geocode(name, city=""):
    """Geocode using Nominatim."""
    query = f"{name}, {city}, Tunisia" if city else f"{name}, Tunisia"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "bledi.tn-station-fixer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        pass
    return None, None

with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)

# Find remaining water stations
water = []
for s in seed["stations"]:
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None: continue
    if in_any_water(lat, lon):
        water.append(s)

print(f"Water stations to geocode: {len(water)}")

fixed = 0
failed = 0

for i, s in enumerate(water):
    name = s.get("name", "")
    city = s.get("city", "")
    
    lat, lon = geocode(name, city)
    if lat and lon and not in_any_water(lat, lon):
        s["lat"] = lat
        s["lon"] = lon
        fixed += 1
        if fixed <= 10:
            print(f"  Fixed {s['id']}: ({lat:.4f}, {lon:.4f})")
    else:
        failed += 1
        if failed <= 10:
            print(f"  FAILED {s['id']}: {name}")
    
    # Rate limit: 1 request per second
    if (i + 1) % 10 == 0:
        print(f"  Progress: {i+1}/{len(water)}")
        time.sleep(1)

print(f"\nFixed: {fixed}")
print(f"Failed: {failed}")

# Verify
water_remaining = [s for s in seed["stations"] if s.get("lat") and s.get("lon") and in_any_water(s["lat"], s["lon"])]
print(f"Water stations remaining: {len(water_remaining)}")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)
print("Wrote seed")
