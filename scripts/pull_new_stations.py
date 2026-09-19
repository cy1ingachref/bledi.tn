#!/usr/bin/env python3
"""Pull full station details for new IDs discovered by the sweep.

Queries station_details.php?id=X for each new ID and merges into
the existing enriched station details file.
"""
import json
import time
import urllib.request
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")
API = "https://www.tunismapper.com/backend/api/station_details.php"
OUT = BASE / "scripts/tunismapper_station_details.json"


def fetch(sid, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"{API}?id={sid}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; bledi.tn-data/1.0)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                return None
            time.sleep(0.3)
    return None


def main():
    # Load existing enriched data
    with open(OUT, encoding="utf-8") as f:
        enriched = json.load(f)

    # Load sweep IDs
    with open(BASE / "scripts/tunismapper_station_ids_full.json", encoding="utf-8") as f:
        sweep = json.load(f)

    sweep_ids = set(sweep["valid_ids"])
    enriched_ids = {int(k) for k in enriched["stations"]}
    new_ids = sorted(sweep_ids - enriched_ids)

    print(f"Pulling {len(new_ids)} new station IDs...")
    t0 = time.time()

    pulled = 0
    failed = []
    for sid in new_ids:
        data = fetch(sid)
        if data and data.get("stop_id"):
            enriched["stations"][str(sid)] = data
            pulled += 1
            nlines = len(data.get("lines", []))
            print(f"  [{sid}] OK  {data.get('stop_name', '?')[:45]:45s}  lines={nlines}")
        else:
            failed.append(sid)
            print(f"  [{sid}] FAILED")

        time.sleep(0.2)

    # Update metadata
    enriched["metadata"]["total_stations"] = len(enriched["stations"])
    enriched["metadata"]["last_updated"] = "2026-09-19"
    enriched["metadata"]["new_ids_pulled"] = pulled
    enriched["metadata"]["new_ids_failed"] = len(failed)

    # Save
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print("\n=== DONE ===")
    print(f"Pulled: {pulled}/{len(new_ids)}")
    print(f"Failed: {len(failed)}")
    print(f"Total enriched stations: {len(enriched['stations'])}")
    print(f"Time: {elapsed:.0f}s")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
