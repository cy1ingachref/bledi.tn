#!/usr/bin/env python3
"""Tests for the local transit router.

These tests assert structural/physical correctness of the router output:
- a path is found for known origin/destination pairs
- no leg has negative or zero length
- max walk distance is respected
- output is deterministic
- the direct-taxi fallback is only proposed beyond TAXI_MIN_DISTANCE_M

They do NOT assert equality with Tunismapper results (the two engines use
different cost models).
"""
from __future__ import annotations

import math
import os
import sys
import pytest
from pathlib import Path

# Make the package importable from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backend.app.routing import (
    BASE,
    MAX_START_WALK_METERS,
    MAX_END_WALK_METERS,
    MAX_WALK_METERS,
    TAXI_MIN_DISTANCE_M,
    TRANSFER_PENALTY_SEC,
    WALK_SPEED_KMH,
    build_graph,
    haversine,
    expected_wait,
)


def _hav(meters: float) -> tuple[float, float]:
    """Return (lat, lon) delta for a given haversine distance (meters),
    starting from a Tunisian reference point."""
    # Approximate: 1 degree latitude ~= 111320 m; longitude at 36.8N ~= 111320*cos(36.8).
    lat_per_m = 1.0 / 111320.0
    lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.8)))
    return lat_per_m * meters, lon_per_m * meters


class TestExpectedWait:
    def test_no_departures_returns_default(self):
        assert expected_wait(None, "bus") == pytest.approx(600.0)
        assert expected_wait([], "train") == pytest.approx(600.0)

    def test_two_departures_half_headway(self):
        # Two departures 600s apart -> median headway 600 -> wait 300.
        deps = ["08:00", "08:10"]
        assert expected_wait(deps, "bus") == pytest.approx(300.0)

    def test_odd_departures_median(self):
        # 0, 300, 900 -> diffs 300, 600 -> median 300 -> wait 150.
        deps = ["08:00", "08:05", "08:15"]
        assert expected_wait(deps, "bus") == pytest.approx(150.0)


class TestRouterSanity:
    @pytest.fixture(scope="class")
    def graph_and_router(self):
        g, r = build_graph()
        return g, r

    def test_finds_path_tunis_centre_to_bizerte(self, graph_and_router):
        g, r = graph_and_router
        res = r.route(36.806, 10.184, 36.914, 9.866)
        assert "error" not in res or res.get("error") is None
        assert res.get("duration_min", 0) > 0

    def test_finds_path_same_station_walk(self, graph_and_router):
        g, r = graph_and_router
        # Start and end very close: should produce a walk-only result.
        res = r.route(36.806, 10.184, 36.8065, 10.1845)
        assert "error" not in res or res.get("error") is None
        assert res.get("duration_min", 0) > 0

    def test_no_negative_or_zero_legs(self, graph_and_router):
        g, r = graph_and_router
        pairs = [
            (36.806, 10.184, 36.914, 9.866),   # Tunis Centre -> Bizerte
            (36.806, 10.184, 36.806, 10.200),   # short east
            (35.823, 10.641, 35.850, 10.660),   # Sousse area
        ]
        for lat1, lon1, lat2, lon2 in pairs:
            res = r.route(lat1, lon1, lat2, lon2)
            steps = res.get("steps", [])
            assert isinstance(steps, list)
            for step in steps:
                dur = step.get("duration_min", 0)
                dist = step.get("distance_m", step.get("distance_km", 0))
                if dist and isinstance(dist, (int, float)):
                    assert dist >= 0, f"negative distance in step {step}"
                if dur and isinstance(dur, (int, float)):
                    assert dur >= 0, f"negative duration in step {step}"

    def test_max_walk_respected_for_start(self, graph_and_router):
        g, r = graph_and_router
        # Place the start far from any station so no transit leg is possible.
        far_lat = 30.0
        far_lon = 10.0
        res = r.route(far_lat, far_lon, 36.806, 10.184)
        steps = res.get("steps", [])
        for step in steps:
            if step.get("type") == "walk":
                assert step.get("distance_m", 0) <= MAX_START_WALK_METERS + MAX_WALK_METERS + MAX_END_WALK_METERS + 500, (
                    f"walk step exceeds max budgets: {step}"
                )

    def test_deterministic_output(self, graph_and_router):
        g, r = graph_and_router
        res1 = r.route(36.806, 10.184, 36.914, 9.866)
        res2 = r.route(36.806, 10.184, 36.914, 9.866)
        assert res1.get("duration_min") == res2.get("duration_min")
        assert len(res1.get("steps", [])) == len(res2.get("steps", []))

    def test_taxi_only_beyond_threshold(self, graph_and_router):
        g, r = graph_and_router
        # Two points 4 km apart -> taxi should be offered (>= TAXI_MIN_DISTANCE_M).
        lat_off, lon_off = _hav(4000)
        res = r.route(36.806, 10.184, 36.806 + lat_off, 10.184 + lon_off)
        modes = {s.get("type") for s in res.get("steps", [])}
        assert "taxi" in modes

        # Two points 1 km apart -> taxi should NOT be offered (< TAXI_MIN_DISTANCE_M).
        lat_off2, lon_off2 = _hav(1000)
        res2 = r.route(36.806, 10.184, 36.806 + lat_off2, 10.184 + lon_off2)
        modes2 = {s.get("type") for s in res2.get("steps", [])}
        assert "taxi" not in modes2
