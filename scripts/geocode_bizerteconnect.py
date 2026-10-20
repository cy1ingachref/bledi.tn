"""Geocode BizerteConnect stations that are in water using Nominatim."""
import json
import time
import urllib.request
import urllib.parse

# Stations that need geocoding (currently in water)
STATIONS_TO_GEOCODE = [
    ("bc_el_alia", "El Alia, Bizerte, Tunisia"),
    ("bc_ras_el_jebel", "Ras El Jebel, Bizerte, Tunisia"),
    ("bc_metline", "El Metline, Bizerte, Tunisia"),
    ("bc_rafraf", "Rafraf, Bizerte, Tunisia"),
    ("bc_utique", "Utique, Bizerte, Tunisia"),
    ("bc_el_blat", "El Blat, Bizerte, Tunisia"),
    ("bc_el_garia", "El Garia, Bizerte, Tunisia"),
    ("bc_el_hammari", "El Hammari, Bizerte, Tunisia"),
    ("bc_es_saoudia", "Es Saoudia, Bizerte, Tunisia"),
    ("bc_beni_toun", "Béni Toun, Bizerte, Tunisia"),
    ("bc_ezzaghrour", "Ezzaghrour, Bizerte, Tunisia"),
    ("bc_oumhani", "Oum Hani, Bizerte, Tunisia"),
    ("bc_sidi_yahia", "Sidi Yahia, Bizerte, Tunisia"),
    ("bc_eschallahmia", "Echellaghmia, Bizerte, Tunisia"),
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

results = {}
for sid, query in STATIONS_TO_GEOCODE:
    lat, lon = geocode(query)
    if lat and lon:
        results[sid] = (lat, lon)
        print(f"  {sid}: ({lat:.4f}, {lon:.4f})")
    else:
        print(f"  {sid}: FAILED")
    time.sleep(1)  # Nominatim rate limit

print(f"\nGeocoded {len(results)}/{len(STATIONS_TO_GEOCODE)} stations")

# Save results
with open(r"C:\Users\cy1in\bledi.tn\data\bizerteconnect_geocoded.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved to data/bizerteconnect_geocoded.json")
