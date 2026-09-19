#!/usr/bin/env python3
"""Fetch ALL bus lines from BizerteConnect API (131 lines, paginated)."""
import urllib.request, json, time, sys

BASE = "https://www.bizerteconnect.com/api/v1/bus-lines/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; bledi.tn-data/1.0)"}
OUT = "scripts/bizerteconnect_all_lines.json"

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("Fetching all BizerteConnect bus lines...")
    all_lines = []
    url = BASE
    page = 1
    while url:
        data = fetch(url)
        batch = data.get("results", [])
        all_lines.extend(batch)
        print(f"  page {page}: +{len(batch)} lines  (total: {len(all_lines)}/{data.get('count','?')})")
        url = data.get("next")
        page += 1
        time.sleep(0.5)

    print(f"\n=== ALL {len(all_lines)} LINES FETCHED ===\n")

    # Examine full structure of first entry
    if all_lines:
        print("=== FULL FIRST ENTRY STRUCTURE ===")
        print(json.dumps(all_lines[0], indent=2, ensure_ascii=False))
        print()

    # Summary: types, line numbers
    types = {}
    for line in all_lines:
        t = line.get("type", "?")
        types[t] = types.get(t, 0) + 1
    print("=== LINE TYPES ===")
    for t, c in sorted(types.items()):
        print(f"  {t}: {c}")

    # Line numbers
    nums = [l.get("number", "?") for l in all_lines]

    # Origin/destination pairs
    od_pairs = set()
    for l in all_lines:
        o = l.get("origin") or l.get("origin_en") or "?"
        d = l.get("destination") or l.get("destination_en") or "?"
        od_pairs.add((o, d))
    print(f"\n=== UNIQUE ORIGIN-DESTINATION PAIRS: {len(od_pairs)} ===")

    # Unique origins
    origins = sorted({l.get("origin") or l.get("origin_en") for l in all_lines})
    print(f"\n=== UNIQUE ORIGINS ({len(origins)}) ===")
    for o in origins:
        print(f"  {o}")

    # Unique destinations
    dests = sorted({l.get("destination") or l.get("destination_en") for l in all_lines})
    print(f"\n=== UNIQUE DESTINATIONS ({len(dests)}) ===")
    for d in dests:
        print(f"  {d}")

    # Save
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_lines, f, indent=2, ensure_ascii=False)
    print(f"\n\nSaved -> {OUT}")

if __name__ == "__main__":
    main()
