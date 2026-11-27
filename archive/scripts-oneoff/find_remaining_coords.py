"""Find correct coordinates for remaining BizerteConnect stations from existing seed data."""
import json
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(x))

# Load seed
with open(r"C:\Users\cy1in\bledi.tn\data\seed_all_tunisia_routes.tagged.json") as f:
    seed = json.load(f)

# Load geocoded results
with open(r"C:\Users\cy1in\bledi.tn\data\bizerteconnect_geocoded.json") as f:
    geocoded = json.load(f)

# Failed stations
FAILED = ["bc_el_blat", "bc_el_hammari", "bc_es_saoudia", "bc_ezzaghrour", "bc_eschallahmia"]

# Search for these towns in the seed by name
for sid in FAILED:
    # Extract town name from station ID
    town = sid.replace("bc_", "").replace("_", " ")
    
    # Search for stations with similar names
    matches = []
    for s in seed["stations"]:
        name = s.get("name", "").lower()
        if town.lower() in name or name in town.lower():
            lat = s.get("lat")
            lon = s.get("lon")
            if lat and lon and lat != 0 and lon != 0:
                matches.append((s["id"], s.get("name","?"), lat, lon, s.get("source","?")))
    
    print(f"\n{sid} ({town}):")
    if matches:
        for m in matches[:5]:
            print(f"  {m[0]:40} {m[1][:30]:32} ({m[2]:.4f}, {m[3]:.4f}) {m[4]}")
    else:
        print("  No matches found")

# Also check the raw BizerteConnect data for these stations
print("\n=== Raw BizerteConnect data ===")
with open(r"C:\Users\cy1in\Downloads\tunisia-transport-data\06-docs-tools\TunisiaTransport-repo\data\seed_lines_bizerte.json") as f:
    biz = json.load(f)

biz_stations = {s["id"]: s for s in biz.get("stations", [])}

for sid in FAILED:
    raw_id = sid.replace("bc_", "")
    raw = biz_stations.get(raw_id)
    if raw:
        print(f"  {sid}: raw=({raw.get('lat',0):.4f}, {raw.get('lon',0):.4f}) name={raw.get('name_fr') or raw.get('name_ar')}")
    else:
        print(f"  {sid}: not found in raw data")
