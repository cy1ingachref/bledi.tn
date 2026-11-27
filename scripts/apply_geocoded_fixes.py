"""Apply geocoded coordinates and remove ungeocodable stations."""
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
import json

# Load seed
with open(REPO / "data" / "seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)

# Load geocoded results
with open(REPO / "data" / "bizerteconnect_geocoded.json") as f:
    geocoded = json.load(f)

# Stations to remove (can't geocode, no line references, wrong coords in water)
REMOVE = ["bc_el_blat", "bc_el_hammari", "bc_es_saoudia", "bc_ezzaghrour", "bc_eschallahmia"]

stations = seed["stations"]
print(f"Before: {len(stations)} stations")

# Apply geocoded coordinates
fixed = 0
for s in stations:
    sid = s["id"]
    if sid in geocoded:
        new_lat, new_lon = geocoded[sid]
        old_lat, old_lon = s["lat"], s["lon"]
        if abs(old_lat - new_lat) > 0.0001 or abs(old_lon - new_lon) > 0.0001:
            print(f"  Fixed {sid}: ({old_lat:.4f}, {old_lon:.4f}) -> ({new_lat:.4f}, {new_lon:.4f})")
            s["lat"] = new_lat
            s["lon"] = new_lon
            fixed += 1

print(f"\nFixed {fixed} stations with geocoded coordinates")

# Remove ungeocodable stations
before = len(stations)
seed["stations"] = [s for s in stations if s["id"] not in REMOVE]
removed = before - len(seed["stations"])
print(f"Removed {removed} ungeocodable stations")

# Verify
bc_stations = [s for s in seed["stations"] if s.get("source") == "bizerteconnect-api"]
print(f"\nAfter: {len(seed['stations'])} stations, {len(bc_stations)} BizerteConnect")

# Check for remaining issues
issues = []
for s in bc_stations:
    sid = s["id"]
    lat = s.get("lat", 0)
    lon = s.get("lon", 0)
    
    # Check if in Bizerte area
    if not (36.9 <= lat <= 37.5 and 9.4 <= lon <= 10.2):
        issues.append((sid, s.get("name","?"), lat, lon, "outside Bizerte area"))

print(f"Remaining issues: {len(issues)}")
for sid, name, lat, lon, reason in issues:
    print(f"  {sid:40} {name[:30]:32} ({lat:.4f}, {lon:.4f}) {reason}")

# Write
with open(REPO / "data" / "seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)

print(f"\nWrote seed with {len(seed['stations'])} stations")
