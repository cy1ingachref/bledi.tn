#!/usr/bin/env python3
"""Offline analysis to choose a city-grouping strategy for the station map.

Single-link clustering at 12 km chains the whole country into one 1 561-station
blob (rural stops chain transit hubs together). Complete-link or a
centre-based approach is needed, and every city needs a real name.

This script evaluates the options against the seed so the choice in
`station_city.dart` is based on measured output, not guesswork.

    python tool/analyze_city_grouping.py
"""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path

SEED = Path("data/seed_all_tunisia_routes.tagged.json")
EARTH_R = 6371.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    )
    return 2 * EARTH_R * math.asin(math.sqrt(a))


# The 24 Tunisian governorates, with their administrative seat coordinates.
# Used as city centres; the seed itself has no governorate field.
GOVERNORATE_SEATS = [
    ("Tunis", 36.8065, 10.1815),
    ("Ariana", 36.8628, 10.1957),
    ("Ben Arous", 36.7520, 10.2220),
    ("Manouba", 36.8161, 10.1011),
    ("Nabeul", 36.4560, 10.7376),
    ("Zaghouan", 36.4028, 10.1425),
    ("Bizerte", 37.2744, 9.8739),
    ("Béja", 36.7256, 9.1817),
    ("Jendouba", 36.5008, 8.7806),
    ("Le Kef", 36.1742, 8.7147),
    ("Siliana", 36.3667, 9.2167),
    ("Kairouan", 35.6781, 10.0963),
    ("Kassab", 35.1833, 8.8000),
    ("Sidi Bouzid", 36.4044, 9.4844),
    ("Sousse", 35.8256, 10.6360),
    ("Monastir", 35.7777, 10.8263),
    ("Mahdia", 35.5047, 11.0622),
    ("Sfax", 34.7406, 10.7603),
    ("Kébili", 33.8814, 8.8742),
    ("Gabès", 33.8815, 10.0982),
    ("Médenine", 33.3547, 10.5052),
    ("Tataouine", 32.9291, 10.4517),
    ("Ghorbel", 35.2292, 9.1789),
    ("Tozeur", 33.9197, 6.9440),
]


def load_stations():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return [
        s
        for s in data["stations"]
        if s.get("lat") and s.get("lon") and s["lat"] and s["lon"]
    ]


def nearest_seat(stations, max_km=60.0):
    """Assign each station to its closest governorate seat."""
    out = collections.defaultdict(list)
    dropped = []
    for s in stations:
        best, best_d = None, 1e9
        for name, lat, lon in GOVERNORATE_SEATS:
            d = haversine_km(s["lat"], s["lon"], lat, lon)
            if d < best_d:
                best, best_d = name, d
        if best_d > max_km:
            dropped.append((s["name"], best, round(best_d, 1)))
            continue
        out[best].append(s)
    return out, dropped


def single_link(stations, radius_km=12.0):
    """Region growing at [radius_km]; chains, so it over-merges."""
    n = len(stations)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = radius_km / 111.0
    grid = collections.defaultdict(list)
    for i, s in enumerate(stations):
        grid[(int(s["lat"] // cell), int(s["lon"] // cell))].append(i)

    for (gy, gx), idxs in grid.items():
        cand = set(idxs)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cand |= set(grid.get((gy + dy, gx + dx), []))
        for i in idxs:
            for j in cand:
                if j <= i:
                    continue
                d = haversine_km(
                    stations[i]["lat"],
                    stations[i]["lon"],
                    stations[j]["lat"],
                    stations[j]["lon"],
                )
                if d <= radius_km:
                    a, b = find(i), find(j)
                    if a != b:
                        parent[a] = b

    comp = collections.defaultdict(list)
    for i in range(n):
        comp[find(i)].append(stations[i])
    return comp


def report(name, groups):
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    print(f"\n--- {name}: {len(groups)} groups")
    print(f"    sizes: {sizes[:18]}")
    print(f"    singletons: {sum(1 for s in sizes if s == 1)}")
    return sizes


def main() -> None:
    stations = load_stations()
    print(f"located stations: {len(stations)}")

    # Option A: single-link. Included to document why it is rejected.
    report("single-link 12km", single_link(stations, 12.0))

    # Option B: nearest governorate seat with a distance cap.
    for cap in (25, 40, 60):
        groups, dropped = nearest_seat(stations, cap)
        sizes = report(f"nearest-seat cap={cap}km", groups)
        if dropped:
            print(f"    dropped (> {cap} km): {len(dropped)} e.g. {dropped[:3]}")

    # Show how the biggest metro-area group splits across seats, since that is
    # the difference between "Tunis" and "Ariana/Manouba/Ben Arous".
    groups, _ = nearest_seat(stations, 60.0)
    print("\nper-governorate station counts:")
    for name, items in sorted(
        groups.items(), key=lambda kv: -len(kv[1])
    ):
        modes = collections.Counter(s.get("mode") for s in items)
        print(f"    {name:12s} {len(items):5d}  {dict(modes)}")


if __name__ == "__main__":
    main()