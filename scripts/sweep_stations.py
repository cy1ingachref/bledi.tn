#!/usr/bin/env python3
"""Full sweep of Tunismapper station_details.php?id=X from 1 to 9000.

Uses HEAD requests to map which station IDs exist without downloading
full JSON data. Records valid IDs to a file for later bulk-fetching.

Stops after 250 consecutive misses (ID gap > 250 means we're past the data).
"""
import json
import time
import urllib.request

API = "https://www.tunismapper.com/backend/api/station_details.php"
OUT = "scripts/tunismapper_station_sweep.json"


def check_exists(sid, retries=2):
    """Return True if station exists (HEAD request)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"{API}?id={sid}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; bledi.tn-data/1.0)"},
                method="HEAD",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if attempt == retries - 1:
                return False
            time.sleep(0.2)
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                return False
            time.sleep(0.2)
    return False


def main():
    results = {}
    consecutive_misses = 0
    max_misses = 250
    max_id = 9000

    print(f"Sweeping station IDs 1 to {max_id}...")
    t0 = time.time()

    for sid in range(1, max_id + 1):
        if check_exists(sid):
            consecutive_misses = 0
            try:
                req = urllib.request.Request(
                    f"{API}?id={sid}",
                    headers={"User-Agent": "Mozilla/5.0 (compatible; bledi.tn-data/1.0)"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                results[str(sid)] = data
                nlines = len(data.get("lines", []))
                print(f"  [{sid}] OK  {data.get('stop_name', '?')[:45]:45s}  lines={nlines}")
            except (urllib.error.HTTPError, urllib.error.URLError, OSError):
                pass
        else:
            consecutive_misses += 1
            if consecutive_misses >= max_misses:
                print(f"  [{sid}] {consecutive_misses} consecutive misses -> stopping")
                break

        time.sleep(0.15)

    # Save
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "total_stations": len(results),
                    "id_range": f"{min(results)}-{max(results)}" if results else "none",
                    "date": "2026-09-19",
                },
                "stations": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    elapsed = time.time() - t0
    print("\n=== DONE ===")
    print(f"Stations found: {len(results)}")
    if results:
        print(f"ID range: {min(results)}-{max(results)}")
    print(f"Time: {elapsed:.0f}s")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
