"""Geocode remaining BizerteConnect stations using Overpass API."""
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
import json
import time
import urllib.request
import urllib.parse

# Failed stations
FAILED = [
    ("bc_el_blat", "El Blat"),
    ("bc_el_hammari", "El Hammari"),
    ("bc_es_saoudia", "Es Saoudia"),
    ("bc_ezzaghrour", "Ezzaghrour"),
    ("bc_eschallahmia", "Echellaghmia"),
]

def geocode_overpass(name):
    """Geocode using Overpass API."""
    query = f"""
    [out:json][timeout:10];
    area["name"="Bizerte"]->.searchArea;
    (
      node["name"="{name}"](area.searchArea);
      way["name"="{name}"](area.searchArea);
      relation["name"="{name}"](area.searchArea);
    );
    out center 1;
    """
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "bledi.tn-station-fixer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            elements = result.get("elements", [])
            if elements:
                elem = elements[0]
                if "center" in elem:
                    return elem["center"]["lat"], elem["center"]["lon"]
                elif "lat" in elem and "lon" in elem:
                    return elem["lat"], elem["lon"]
    except Exception as e:
        print(f"  Error: {e}")
    return None, None

# Load existing results
with open(REPO / "data" / "bizerteconnect_geocoded.json") as f:
    results = json.load(f)

for sid, name in FAILED:
    if sid in results:
        print(f"  {sid}: already geocoded, skipping")
        continue
    lat, lon = geocode_overpass(name)
    if lat and lon:
        results[sid] = (lat, lon)
        print(f"  {sid}: ({lat:.4f}, {lon:.4f})")
    else:
        print(f"  {sid}: FAILED")
    time.sleep(1)

print(f"\nTotal geocoded: {len(results)}/14")

# Save results
with open(REPO / "data" / "bizerteconnect_geocoded.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved to data/bizerteconnect_geocoded.json")
