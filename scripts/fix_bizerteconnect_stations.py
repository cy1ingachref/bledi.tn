"""Fix BizerteConnect station issues:
1. Fix 14 stations in water (geocode correctly)
2. Remove 1 station outside Bizerte area (bc_aeroport_tunis)
3. Fix 2 stations with wrong coordinates (bc_ain_el_berda, bc_el_blat)
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

# Known correct coordinates for Bizerte-area towns
CORRECT_COORDS = {
    "bc_el_alia": (37.2300, 10.0300),      # El Alia - inland
    "bc_ras_el_jebel": (37.2100, 10.1400),  # Ras El Jebel - inland
    "bc_metline": (37.2500, 10.0700),       # El Metline - inland
    "bc_rafraf": (37.1900, 10.2000),        # Rafraf - inland
    "bc_utique": (37.0500, 10.0500),        # Utique - inland
    "bc_el_blat": (37.1400, 10.0200),       # El Blat - inland
    "bc_el_garia": (37.2200, 10.1000),      # El Garia - inland
    "bc_el_hammari": (37.2300, 10.1300),    # El Hammari - inland
    "bc_es_saoudia": (37.2500, 10.0000),    # Es Saoudia - inland
    "bc_beni_toun": (37.1000, 10.0500),     # Béni Toun - inland
    "bc_ezzaghrour": (37.1600, 10.0800),    # Ezzaghrour - inland
    "bc_oumhani": (37.1400, 10.1000),       # Oum Hani - inland
    "bc_sidi_yahia": (37.1700, 10.1200),    # Sidi Yahia - inland
    "bc_eschallahmia": (37.1900, 10.1500),  # Echellaghmia - inland
    "bc_ain_el_berda": (37.2200, 9.9300),   # Ain El Berda - fix 6.3km offset
}

# Load seed
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)

stations = seed["stations"]
print(f"Before: {len(stations)} stations")

# 1. Fix 14 stations in water + bc_ain_el_berda
fixed = 0
for s in stations:
    sid = s["id"]
    if sid in CORRECT_COORDS:
        new_lat, new_lon = CORRECT_COORDS[sid]
        old_lat, old_lon = s["lat"], s["lon"]
        if abs(old_lat - new_lat) > 0.0001 or abs(old_lon - new_lon) > 0.0001:
            print(f"  Fixed {sid}: ({old_lat:.4f}, {old_lon:.4f}) -> ({new_lat:.4f}, {new_lon:.4f})")
            s["lat"] = new_lat
            s["lon"] = new_lon
            fixed += 1

print(f"\nFixed {fixed} stations")

# 2. Remove bc_aeroport_tunis (outside Bizerte area)
before = len(stations)
seed["stations"] = [s for s in stations if s["id"] != "bc_aeroport_tunis"]
removed = before - len(seed["stations"])
print(f"Removed {removed} station (bc_aeroport_tunis)")

# 3. Verify
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
    
    # Check against known coords
    if sid in CORRECT_COORDS:
        exp_lat, exp_lon = CORRECT_COORDS[sid]
        dist = haversine(lat, lon, exp_lat, exp_lon)
        if dist > 1000:
            issues.append((sid, s.get("name","?"), lat, lon, f"{dist:.0f}m from expected"))

print(f"\nRemaining issues: {len(issues)}")
for sid, name, lat, lon, reason in issues:
    print(f"  {sid:40} {name[:30]:32} ({lat:.4f}, {lon:.4f}) {reason}")

# Write
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json", "w", encoding="utf-8") as f:
    json.dump(seed, f, ensure_ascii=False, indent=1)

print(f"\nWrote seed with {len(seed['stations'])} stations")
