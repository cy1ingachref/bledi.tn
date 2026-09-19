#!/usr/bin/env python3
"""Scrape ALL Tunismapper line details across the full ID range.

Uses a two-phase approach:
  Phase 1: Scan IDs 1-700 (trains, RFR, metro lines)
  Phase 2: Scan IDs 700-900 (bus lines)

Handles large gaps in the ID sequence by using a high miss threshold
and iterating through all IDs.
"""
import urllib.request, re, json, time, sys

BASE = "https://www.tunismapper.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == retries - 1:
                return ""
            time.sleep(1)


def extract_stops_from_html(html):
    json_match = re.search(r'var\s+\w+\s*=\s*(\[.*?"stop_id".*?\]);', html, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            return []
    return []


def extract_route_info(html):
    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    if title_match:
        title = title_match.group(1)
        parts = title.split(" - ")
        if len(parts) >= 2:
            route_type_name = parts[0]
            type_match = re.match(r'Ligne de\s+(\S+)\s+(.*)', route_type_name)
            if type_match:
                transport_type = type_match.group(1)
                route_number = type_match.group(2).strip()
                return transport_type, route_number
    return "unknown", "?"


def main():
    # Phase 1: IDs 1-700 (trains, RFR, metro)
    # Phase 2: IDs 700-900 (buses)
    PHASE_BREAK = 700
    MAX_ID = 900
    MAX_MISSES = 250

    all_results = []

    for phase, (start, end) in enumerate([(1, PHASE_BREAK), (PHASE_BREAK, MAX_ID + 1)], 1):
        print(f"\n{'='*60}")
        print(f"PHASE {phase}: route_id {start} to {end - 1}")
        print(f"{'='*60}\n")

        consecutive_misses = 0

        for route_id in range(start, end):
            detail_url = f"{BASE}/ligne_details.php?route_id={route_id}"
            html = fetch(detail_url)

            if not html:
                consecutive_misses += 1
                if consecutive_misses >= MAX_MISSES:
                    print(f"  [{route_id}] {consecutive_misses} consecutive misses — stopping phase")
                    break
                continue

            stops = extract_stops_from_html(html)
            transport_type, route_number = extract_route_info(html)

            if not stops:
                consecutive_misses += 1
                if consecutive_misses >= MAX_MISSES:
                    print(f"  [{route_id}] {consecutive_misses} consecutive misses — stopping phase")
                    break
                continue

            consecutive_misses = 0
            total_stops = sum(r["stop_count"] for r in all_results) + len(stops)

            print(f"  [{route_id}] {transport_type} {route_number}: {len(stops)} stops (running total: {total_stops})")

            all_results.append({
                "route_id": str(route_id),
                "transport_type": transport_type,
                "route_number": route_number,
                "stops": stops,
                "stop_count": len(stops),
            })

            time.sleep(0.3)

    # Save results
    out_file = "scripts/tunismapper_all_routes_stops.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "total_routes": len(all_results),
                "total_stops": sum(r["stop_count"] for r in all_results),
                "date": "2026-09-19",
            },
            "routes": all_results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"DONE — Phase 1+2 combined")
    print(f"Routes with stops: {len(all_results)}")
    print(f"Total stops: {sum(r['stop_count'] for r in all_results)}")
    print(f"Saved -> {out_file}")
    print(f"{'='*60}")

    # Print summary by transport type
    from collections import Counter
    types = Counter(r["transport_type"] for r in all_results)
    print(f"\nBy transport type:")
    for t, c in sorted(types.items()):
        type_stops = sum(r["stop_count"] for r in all_results if r["transport_type"] == t)
        print(f"  {t}: {c} routes, {type_stops} stops")


if __name__ == "__main__":
    main()
