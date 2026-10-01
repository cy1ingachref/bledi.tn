#!/usr/bin/env python3
"""Sanity-check the edited backend module without starting the server.

Imports `src.backend.app.main` and exercises the pure helpers, so a syntax or
import error is caught before the server is restarted.
"""

import sys

sys.path.insert(0, ".")

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

# The Tunis core must resolve to Tunis, not a neighbouring governorate.
cases = [
    (36.8065, 10.1815, "Tunis", "Tunis city centre"),
    (36.8628, 10.1957, "Ariana", "Ariana"),
    (36.7520, 10.2220, "Ben Arous", "Ben Arous"),
    (35.8256, 10.6360, "Sousse", "Sousse"),
    (37.2744, 9.8739, "Bizerte", "Bizerte"),
    (34.7406, 10.7603, "Sfax", "Sfax"),
]
for lat, lon, expected, label in cases:
    got = nearest_city(lat, lon)
    ok = got == expected
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: {got} (expected {expected})")
    if not ok:
        bad.append(f"{label} -> {got}, expected {expected}")

# Remote villages must land in the explicit bucket, never a wrong governorate.
for lat, lon, label in [(35.09, 10.55, "Sened area"), (33.66, 10.30, "Maknassy area")]:
    got = nearest_city(lat, lon)
    print(f"  {'OK  ' if got == UNASSIGNED_CITY else 'note'} {label}: {got}")

# Every station must resolve to a non-empty city key.
unresolved = [s["id"] for s in _stations if s.get("lat") and s.get("lon")
              and not nearest_city(s["lat"], s["lon"])]
print(f"  stations with no city: {len(unresolved)}")
if unresolved:
    bad.append(f"{len(unresolved)} stations resolve to an empty city")

print(f"\n  city seats: {len(CITY_SEATS)}, max distance {MAX_CITY_DISTANCE_KM} km")
print(f"  louage stops: {len(_LOUAGE_STATIONS)}, routes indexed: {len(_LOUAGE_ROUTES_BY_STOP)}")

# Mode must be present on every transit station the colouring depends on.
missing_mode = [s["id"] for s in _stations
                if s.get("lat") and s.get("lon") and not s.get("mode")]
print(f"  stations without mode: {len(missing_mode)}")

for b in bad:
    print("FAIL:", b)
sys.exit(1 if bad else 0)