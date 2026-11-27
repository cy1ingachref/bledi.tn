"""Geocode remaining BizerteConnect stations with alternative queries."""
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
import json
import time
import urllib.request
import urllib.parse

# Failed stations with alternative queries
STATIONS_TO_GEOCODE = [
    ("bc_el_blat", "El Blat, Bizerte"),
    ("bc_el_blat", "Blat, Bizerte, Tunisia"),
    ("bc_el_hammari", "El Hammari, Bizerte"),
    ("bc_el_hammari", "Hammari, Bizerte, Tunisia"),
    ("bc_es_saoudia", "Es Saoudia, Bizerte"),
    ("bc_es_saoudia", "Saoudia, Bizerte, Tunisia"),
    ("bc_ezzaghrour", "Ezzaghrour, Bizerte"),
    ("bc_ezzaghrour", "Zaghrour, Bizerte, Tunisia"),
    ("bc_sidi_yahia", "Sidi Yahia, Bizerte"),
    ("bc_sidi_yahia", "Sidi Yahia, Tunisia"),
    ("bc_eschallahmia", "Echellaghmia, Bizerte"),
    ("bc_eschallahmia", "Echallahmia, Bizerte, Tunisia"),
]

def geocode(query):
    """Geocode using Nominatim."""
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
        print(f"  Error: {e}")
    return None, None

# Load existing results
with open(REPO / "data" / "bizerteconnect_geocoded.json") as f:
    results = json.load(f)

for sid, query in STATIONS_TO_GEOCODE:
    if sid in results:
        print(f"  {sid}: already geocoded, skipping")
        continue
    lat, lon = geocode(query)
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
