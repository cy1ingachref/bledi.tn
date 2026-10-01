#!/usr/bin/env python3
"""Sanity-check the backend's station→city assignment without starting it.

Run from anywhere; the backend package is located relative to this file:

    python tool/check_backend_city.py

Imports `src.backend.app.main` (which needs the repository root on sys.path) and
exercises the pure helpers, so a syntax or import error surfaces here rather
than at server start.
"""

import sys
from pathlib import Path

# src/mobile/tool/ -> src/mobile/ -> src/ -> repo root
REPO = Path(__file__).resolve().parents[3]
if not (REPO / "src" / "backend" / "app" / "main.py").is_file():
    sys.exit(f"backend not found under {REPO}")
sys.path.insert(0, str(REPO))

from src.backend.app.main import (  # noqa: E402
    CITY_SEATS,
    MAX_CITY_DISTANCE_KM,
    UNASSIGNED_CITY,
    _LOUAGE_ROUTES_BY_STOP,
    _LOUAGE_STATIONS,
    _stations,
    nearest_city,
)

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