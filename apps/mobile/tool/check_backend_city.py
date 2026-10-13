#!/usr/bin/env python3
"""Sanity-check the backend's station→city assignment without starting it.

Needs the transit service installed (`pip install -e services/transit`):

    python apps/mobile/tool/check_backend_city.py

Exercises the pure helpers on the real seed, so a syntax or import error
surfaces here rather than at server start.
"""

import sys
from pathlib import Path

from bledi_transit.adapters.seed_files import SeedFileNetwork
from bledi_transit.domain.cities import CITY_SEATS, MAX_CITY_DISTANCE_KM, nearest_city

# apps/mobile/tool/ -> apps/mobile/ -> apps/ -> repo root
REPO = Path(__file__).resolve().parents[3]
network = SeedFileNetwork(REPO / "data").load()
_stations = network.stations
_LOUAGE_STATIONS = network.louage_stations
_LOUAGE_ROUTES_BY_STOP = network.louage_routes_by_stop

bad = []

# Known governorate seats must resolve to themselves.
for lat, lon, expected in [
    (36.8065, 10.1815, "Tunis"),
    (36.8628, 10.1957, "Ariana"),
    (36.7520, 10.2220, "Ben Arous"),
    (35.8256, 10.6360, "Sousse"),
    (37.2744, 9.8739, "Bizerte"),
    (34.7406, 10.7603, "Sfax"),
]:
    got = nearest_city(lat, lon)
    ok = got == expected
    print(f"  {'OK  ' if ok else 'FAIL'} {expected}: {got}")
    bad += [] if ok else [f"{expected} -> {got}"]

# Every located station must land in some city, never an empty key.
located = [s for s in _stations if s.get("lat") and s.get("lon")]
unresolved = [s["id"] for s in located if not nearest_city(s["lat"], s["lon"])]
print(f"  located stations: {len(located)}, unresolved: {len(unresolved)}")
bad += [f"{len(unresolved)} stations resolve to an empty city"] if unresolved else []

# The mode field drives the map colours; the seed must supply it.
missing_mode = [s["id"] for s in located if not s.get("mode")]
print(f"  stations without mode: {len(missing_mode)}")
bad += [f"{len(missing_mode)} stations have no mode"] if missing_mode else []

print(f"  seats: {len(CITY_SEATS)}, cutoff {MAX_CITY_DISTANCE_KM} km")
print(f"  louage stops: {len(_LOUAGE_STATIONS)}, indexed routes: {len(_LOUAGE_ROUTES_BY_STOP)}")

for b in bad:
    print("FAIL:", b)
sys.exit(1 if bad else 0)