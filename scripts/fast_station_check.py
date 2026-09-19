#!/usr/bin/env python3
"""Fast station ID existence checker.

Uses HEAD requests to map which station IDs exist without downloading
full JSON data. Records valid IDs to a file for later bulk-fetching.

Strategy:
  - HEAD request per ID (no body download)
  - 200 = valid station
  - 404 = not found
  - Stop after 300 consecutive misses (gap too large)
"""
import json
import time
import urllib.request

API = "https://www.tunismapper.com/backend/api/station_details.php"
OUT = "scripts/tunismapper_station_ids.json"


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
    valid_ids = []
    consecutive_misses = 0
    max_misses = 300
    max_id = 9500

    print(f"Fast existence check: station IDs 1 to {max_id}...")
    print("Using HEAD requests (no body download)")
    t0 = time.time()

    for sid in range(1, max_id + 1):
        if check_exists(sid):
            consecutive_misses = 0
            valid_ids.append(sid)
            print(f"  [{sid}] EXISTS ({len(valid_ids)} found so far)")
        else:
            consecutive_misses += 1
            if consecutive_misses >= max_misses:
                print(f"  [{sid}] {consecutive_misses} consecutive misses -> stopping")
                break

        if sid % 500 == 0:
            elapsed = time.time() - t0
            rate = sid / elapsed if elapsed > 0 else 0
            print(f"  ... progress: {sid}/{max_id}, {len(valid_ids)} valid, {rate:.0f} IDs/s")

    # Save
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "total_valid": len(valid_ids),
                    "id_range": f"{min(valid_ids)}-{max(valid_ids)}" if valid_ids else "none",
                    "date": "2026-09-19",
                    "method": "HEAD request existence check",
                },
                "valid_ids": valid_ids,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    elapsed = time.time() - t0
    print("\n=== DONE ===")
    print(f"Valid station IDs: {len(valid_ids)}")
    if valid_ids:
        print(f"ID range: {min(valid_ids)}-{max(valid_ids)}")
    print(f"Time: {elapsed:.0f}s")
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
