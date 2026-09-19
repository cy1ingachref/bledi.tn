#!/usr/bin/env python3
"""Batch-query Tunismapper station_details API for all scraped stop_ids.

Reads tunismapper_all_routes_stops.json, extracts all unique stop_ids,
queries backend/api/station_details.php?id=X for each, and saves
enriched station data (GPS, lines served, colors, directions).
"""
import urllib.request, json, time, sys
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")
API = "https://www.tunismapper.com/backend/api/station_details.php"

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(0.5)

def main():
    # Load scraped routes
    with open(BASE / "scripts/tunismapper_all_routes_stops.json", encoding="utf-8") as f:
        scraped = json.load(f)

    # Extract all unique stop_ids
    stop_ids = set()
    for route in scraped["routes"]:
        for stop in route.get("stops", []):
            sid = stop.get("stop_id")
            if sid:
                stop_ids.add(int(sid))

    print(f"Found {len(stop_ids)} unique stop_ids to query")

    # Query station_details for each
    results = {}
    failed = []
    for i, sid in enumerate(sorted(stop_ids)):
        data = fetch(f"{API}?id={sid}")
        if data and data.get("stop_id"):
            results[str(sid)] = data
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(stop_ids)}] queried ({len(results)} ok, {len(failed)} failed)")
        else:
            failed.append(sid)
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(stop_ids)}] queried ({len(results)} ok, {len(failed)} failed)")

        time.sleep(0.2)

    # Save
    out_file = BASE / "scripts/tunismapper_station_details.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "total_stations": len(results),
                "failed": len(failed),
                "date": "2026-09-19",
            },
            "stations": results,
            "failed_ids": failed,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n=== DONE ===")
    print(f"Stations enriched: {len(results)}")
    print(f"Failed: {len(failed)}")
    print(f"Saved -> {out_file}")

if __name__ == "__main__":
    main()
