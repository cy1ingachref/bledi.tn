#!/usr/bin/env python3
"""Sanity-check data/water_polys.json against known-dry and known-wet points.

A water index that says "in water" for a city centre is worse than no index,
and that is exactly the failure a hole-vs-ring mistake produces: an ocean
polygon carves land out as INNER rings, so testing each ring independently
reports land as water. This asserts the index against ground truth before the
audit is allowed to use it.

    python tool/check_water_index.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tool"))

from audit_station_placement import WaterIndex  # noqa: E402

# Known points. lat, lon, expected_in_water, description.
CASES = [
    (36.8065, 10.1815, False, "Tunis city centre (Avenue Habib Bourguiba)"),
    (36.8008, 10.1800, False, "Tunis Medina"),
    (36.8530, 10.3230, False, "La Marsa (coastal town, on land)"),
    (35.8256, 10.6084, False, "Sousse city centre"),
    (34.7406, 10.7603, False, "Sfax city centre"),
    (37.2740, 9.8740, False, "Bizerte town (on land)"),
    (33.9197, 6.9440, False, "Tozeur (near Chott el Djerid, on land)"),
    # Sea points.
    (37.1000, 10.6000, True, "Gulf of Tunis (open sea)"),
    (36.9000, 10.4000, True, "Gulf of Tunis, north-east"),
    (34.0000, 11.0000, True, "Gulf of Gabes (open sea)"),
    (37.3000, 10.2000, True, "Mediterranean north of Cap Bon"),
    # A big inland chott. OSM maps Chott el Djerid as saltmarsh polygons.
    (33.7000, 8.4000, True, "Chott el Djerid (salt flat)"),
]


def main() -> int:
    path = ROOT / "data" / "water_polys.json"
    if not path.is_file():
        print(f"MISSING: {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    idx = WaterIndex(data.get("elements", []))
    print(f"water index: {len(idx.shapes)} rings from {path.name}\n")

    bad = 0
    for lat, lon, expect_water, desc in CASES:
        hit = idx.contains(lat, lon)
        got_water = hit is not None
        ok = got_water == expect_water
        if not ok:
            bad += 1
        mark = "ok  " if ok else "WRONG"
        verdict = "WATER" if got_water else "dry"
        print(f"  [{mark}] {desc[:44]:44s} -> {verdict:5s}"
              f"{(' (' + hit + ')') if hit else ''}")

    print()
    if bad:
        print(f"FAILED: {bad} of {len(CASES)} points classified wrongly")
        print("If inland cities come back as WATER, the ocean layer is being "
              "tested ring-by-ring and its land holes are reading as water.")
        return 1
    print(f"all {len(CASES)} ground-truth points classified correctly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
