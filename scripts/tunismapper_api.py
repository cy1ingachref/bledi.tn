#!/usr/bin/env python3
"""Tunismapper itinerary API wrapper.

Calls the Tunismapper itinerary.php endpoint with start/end coordinates
and returns the full multi-modal route result (best_fastest, best_less_walk,
alternatives, taxi).

This is the same calculator used by Tunismapper — same data, same results.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")
API = "https://www.tunismapper.com/backend/api/itinerary.php"

# Speed constants (km/h) — used only for map rendering, not for API calls
WALK_SPEED = 5.0
TAXI_SPEED = 40.0


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two points."""
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_route(start_lat, start_lon, end_lat, end_lon):
    """Get multi-modal route from Tunismapper itinerary API.

    Returns dict with:
      - best_fastest: fastest route
      - best_less_walk: route with least walking
      - alternatives: other route options
      - taxi: taxi-only option
      - debug: debugging info
    """
    params = urllib.parse.urlencode({
        "startLat": start_lat,
        "startLng": start_lon,
        "endLat": end_lat,
        "endLng": end_lon,
    })
    url = f"{API}?{params}"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def format_route_summary(result):
    """Format route result into a human-readable summary."""
    bf = result.get("best_fastest", {})
    bl = result.get("best_less_walk", {})
    alts = result.get("alternatives", [])
    taxi = result.get("taxi", {})
    debug = result.get("debug", {})

    lines = []
    lines.append(f"Best fastest: {bf.get('label', '?')} — {bf.get('duration', '?')} min, {bf.get('walk', '?')} min walk, {bf.get('transfers', '?')} transfer(s)")
    lines.append("  Steps:")
    for i, step in enumerate(bf.get("steps", [])):
        if step["type"] == "walk":
            lines.append(f"    [{i+1}] Walk {step['duration']} min ({step.get('stop_name', '?')})")
        elif step["type"] == "transit":
            mode = step.get("mode", "transit")
            lines.append(f"    [{i+1}] {mode.upper()} {step['line']} — {step['duration']} min ({step.get('stop_name', '?')})")
        elif step["type"] == "transfer_walk":
            lines.append(f"    [{i+1}] Transfer walk {step['duration']} min ({step.get('walk_dist', 0)}m)")

    lines.append("")
    lines.append(f"Less walk: {bl.get('label', '?')} — {bl.get('duration', '?')} min, {bl.get('walk', '?')} min walk")
    lines.append(f"Alternatives: {len(alts)}")
    lines.append(f"Taxi: {taxi.get('duration', '?')} min")
    lines.append(f"Debug: {json.dumps(debug, ensure_ascii=False)}")

    return "\n".join(lines)


def main():
    # Test: Tborba to Cite Ennasr 1 (same as user's URL)
    result = get_route(
        start_lat=36.8151533, start_lon=10.0568158,
        end_lat=36.8585478, end_lon=10.1682756,
    )

    print("=== TUNISMAPPER ITINERARY API RESULT ===")
    print(format_route_summary(result))
    print()

    # Save full result
    out_path = BASE / "scripts/tunismapper_route_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Full result saved -> {out_path}")


if __name__ == "__main__":
    main()
