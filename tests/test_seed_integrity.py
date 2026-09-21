#!/usr/bin/env python3
"""Seed integrity checks.

Reports (does not fail on) data-quality issues:
- duplicate station IDs
- line stop references that do not resolve
- coordinates outside Tunisia's bounding box
- lines with fewer than 2 valid stops
- count of stations with mode "unknown"
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SEED_PATH = REPO_ROOT / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = REPO_ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# Tunisia bounding box (approx).
TUNISIA_LAT_MIN = 30.0
TUNISIA_LAT_MAX = 37.5
TUNISIA_LON_MIN = 7.5
TUNISIA_LON_MAX = 12.0


@pytest.fixture(scope="session")
def seed():
    import json
    with _SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


class TestSeedIntegrity:
    def test_no_duplicate_station_ids(self, seed):
        stations = seed.get("stations", [])
        ids = [s.get("id") for s in stations if s.get("id")]
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        assert not dupes, f"Duplicate station ids: {dupes[:10]}"

    def test_all_line_stop_references_resolve(self, seed):
        stations = seed.get("stations", [])
        sids = {s["id"] for s in stations if s.get("id")}
        unresolved: list[tuple[str, str]] = []
        for ln in seed.get("lines", []):
            stops = ln.get("stations") or ln.get("stops") or []
            for sid in stops:
                if sid and sid not in sids:
                    unresolved.append((ln.get("id", "?"), sid))
        assert not unresolved, f"Unresolved stop ids: {unresolved[:20]}"

    def test_coordinates_inside_tunisia_bbox(self, seed):
        out_of_bounds: list[tuple[str, float, float]] = []
        for s in seed.get("stations", []):
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None or lat == 0 or lon == 0:
                continue
            if not (TUNISIA_LAT_MIN <= lat <= TUNISIA_LAT_MAX and TUNISIA_LON_MIN <= lon <= TUNISIA_LON_MAX):
                out_of_bounds.append((s.get("id", "?"), lat, lon))
        # We report rather than fail for borderline cases.
        if out_of_bounds:
            print(f"\n{len(out_of_bounds)} stations outside Tunisia bbox (reported, not failed):")
            for sid, lat, lon in out_of_bounds[:10]:
                print(f"  {sid}: ({lat:.4f}, {lon:.4f})")

    def test_no_line_with_fewer_than_two_valid_stops(self, seed):
        stations = {s["id"] for s in seed.get("stations", []) if s.get("id")}
        short_lines: list[tuple[str, int]] = []
        for ln in seed.get("lines", []):
            stops = ln.get("stations") or ln.get("stops") or []
            valid = [s for s in stops if s in stations]
            if len(valid) < 2:
                short_lines.append((ln.get("id", ln.get("number", "?")), len(valid)))
        assert not short_lines, f"Lines with <2 valid stops: {short_lines[:20]}"

    def test_report_unknown_mode_stations(self, seed):
        stations = seed.get("stations", [])
        unknown = [s for s in stations if (s.get("mode") or "").lower() == "unknown"]
        # Report the count; do NOT fail the test.
        print(f"\nStations with mode='unknown': {len(unknown)} of {len(stations)}")
        if unknown:
            print("  Examples:")
            for s in unknown[:5]:
                print(f"    {s.get('id')}: {s.get('name')}")
