#!/usr/bin/env python3
"""Geocode SNTRI station names using Nominatim (OpenStreetMap).

Takes the 295 SNTRI station names and queries Nominatim for GPS coordinates.
Respects rate limit (1 request/sec). Saves results to JSON.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")
IN = BASE / "scripts/sntri_stations.json"
OUT = BASE / "scripts/sntri_stations_geocoded.json"

NOMINATIM = "https://nominatim.openstreetmap.org/search"


def geocode(name, retries=3):
    """Geocode a station name using Nominatim. Returns (lat, lon) or None."""
    for attempt in range(retries):
        try:
            params = urllib.parse.urlencode({
                "q": name,
                "format": "json",
                "limit": 1,
                "countrycodes": "tn",  # Tunisia only
            })
            url = f"{NOMINATIM}?{params}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "bledi.tn-data/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
                return None
        except (urllib.error.URLError, OSError, ValueError):
            if attempt == retries - 1:
                return None
            time.sleep(1)
    return None


def main():
    # Load SNTRI stations
    with open(IN, encoding="utf-8") as f:
        data = json.load(f)

    stations = data["stations"]
    print(f"Geocoding {len(stations)} SNTRI stations...")
    print("Using Nominatim (1 req/sec, ~5 min)")
    t0 = time.time()

    results = []
    found = 0
    failed = []

    for i, name in enumerate(stations):
        coords = geocode(name)
        if coords:
            lat, lon = coords
            results.append({
                "name": name,
                "lat": lat,
                "lon": lon,
                "source": "nominatim",
            })
            found += 1
            print(f"  [{i+1}/{len(stations)}] {name[:40]:40s} -> {lat:.4f}, {lon:.4f}")
        else:
            failed.append(name)
            print(f"  [{i+1}/{len(stations)}] {name[:40]:40s} -> NOT FOUND")

        time.sleep(1.1)  # Respect Nominatim rate limit

    # Save
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "source": "Nominatim (OpenStreetMap)",
                "total_stations": len(stations),
                "geocoded": found,
                "failed": len(failed),
                "date": "2026-09-19",
            },
            "stations": results,
            "failed_names": failed,
        }, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print("\n=== DONE ===")
    print(f"Geocoded: {found}/{len(stations)} ({found/len(stations)*100:.0f}%)")
    print(f"Failed: {len(failed)}")
    print(f"Time: {elapsed:.0f}s")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
