#!/usr/bin/env python3
"""Targeted fast station ID existence check for the 7000-9500 range.

Uses HEAD requests with a delay to avoid rate-limiting.
Loads existing valid IDs and appends new ones.
"""
import json
import time
import urllib.request

API = "https://www.tunismapper.com/backend/api/station_details.php"
OUT = "scripts/tunismapper_station_ids_full.json"


def check_exists(sid, retries=3):
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
            time.sleep(0.5)
        except (urllib.error.URLError, OSError):
            if attempt == retries - 1:
                return False
            time.sleep(0.5)
    return False


def main():
    # Load existing
    with open(OUT, encoding="utf-8") as f:
        existing = json.load(f)
    valid_ids = set(existing["valid_ids"])
    print(f"Loaded {len(valid_ids)} existing valid IDs")

    # Targeted sweep 7000-9500 with delay
    consecutive_misses = 0
    max_misses = 200
    delay = 0.3

    print(f"Targeted sweep: IDs 7000-9500 (delay={delay}s)...")
    t0 = time.time()

    for sid in range(7000, 9501):
        if check_exists(sid):
            consecutive_misses = 0
            valid_ids.add(sid)
            print(f"  [{sid}] EXISTS ({len(valid_ids)} found so far)")
        else:
            consecutive_misses += 1
            if consecutive_misses >= max_misses:
                print(f"  [{sid}] {consecutive_misses} consecutive misses -> stopping")
                break

        if sid % 500 == 0:
            elapsed = time.time() - t0
            rate = (sid - 7000) / elapsed if elapsed > 0 else 0
            print(f"  ... progress: {sid}/9500, {len(valid_ids)} valid, {rate:.1f} IDs/s")

        time.sleep(delay)

    # Save
    valid_ids = sorted(valid_ids)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "total_valid": len(valid_ids),
                    "id_range": f"{min(valid_ids)}-{max(valid_ids)}" if valid_ids else "none",
                    "date": "2026-09-19",
                    "method": "HEAD request (targeted 7000-9500 with delay)",
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
