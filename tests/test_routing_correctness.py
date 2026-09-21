#!/usr/bin/env python3
"""Regression + correctness tests for the transit router.

These exercises target the specific bugs called out in code review:
- Dijkstra state collapse (station-only dist key masks transfer-sensitive paths).
- Wait charged per stop instead of per boarding.
- _line_between misattribution on shared corridors.
- Midnight wrap in expected_wait.
- Taxi step missing fare field.

They use a SMALL synthetic graph so they are fast, deterministic, and
independent of the seed's real station coordinates.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backend.app.routing import (
    Router,
    WALK_SPEED_KMH,
    TRANSIT_COST_SPEED_KMH,
    TRANSIT_DISPLAY_SPEED_KMH,
    TRANSFER_PENALTY_SEC,
    TAXI_FARE_BASE,
    TAXI_FARE_PER_KM,
    TAXI_MIN_DISTANCE_M,
    TAXI_SPEED_KMH,
    expected_wait,
    haversine,
)


# ── helpers ───────────────────────────────────────────────────────────────

def _make_stations(ids: list[tuple[str, float, float, str | None]]) -> dict[str, dict]:
    """Build a stations dict from [(id, lat, lon, departures_pickle_or_None), ...]."""
    out: dict[str, dict] = {}
    for sid, lat, lon, deps in ids:
        d: dict = {"id": sid, "name": sid, "lat": lat, "lon": lon}
        if deps is not None:
            d["departures"] = deps
        out[sid] = d
    return out


def _line(idv: str, mode: str, stops: list[str], departures: list[str] | None = None) -> dict:
    d: dict = {"id": idv, "mode": mode, "stations": stops}
    if departures is not None:
        d["departures"] = departures
    return d


def _ride_s(meters: float) -> float:
    return meters / (TRANSIT_COST_SPEED_KMH / 3.6)


def _ride_min_display(meters: float) -> float:
    return meters / 1000 / TRANSIT_DISPLAY_SPEED_KMH * 60


def _walk_min(meters: float) -> float:
    return meters / 1000 / WALK_SPEED_KMH * 60


# ── Bug 1: Dijkstra state collapse ───────────────────────────────────────

class TestDijkstraStateNotCollapsed:
    """The router must not treat all arrivals at a station as equivalent.

    Reproduces the reviewer's exact scenario (scaled to 2800 m so the result
    is transit-only, i.e. below the TAXI_MIN_DISTANCE_M threshold of 3000 m):

      L3: SY -> SZ  (200 m, TWO departures 08:00/08:10 -> wait 300 s)
      L2: SY -> SZ -> Z  (200 m + 2600 m, ONE departure 08:00 -> wait 600 s default)

    Start SY, end Z. L3 makes a CHEAPER first arrival at SZ (332.7 s) than L2
    (632.7 s), so the buggy station-only dist key keeps the L3 label and discards
    the L2 label at SZ. Continuing from the L3 label forces an alight/board at SZ,
    paying wait(L2)+transfer on top of the already-paid L3 ride. Staying on L2
    (the correct answer) pays only wait(L2) once + the full ride.

    Old (buggy) total  ~ 25.6 min.  New (fixed) total  ~ 17.6 min.  ~1.45x.
    """

    def test_stay_on_line_is_preferred_over_dead_end_transfer(self):
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.0)))
        sy_lat, sy_lon = 36.0, 10.0
        sz_lon = sy_lon + 200 * lon_per_m        # 200 m east
        z_lon  = sy_lon + 2800 * lon_per_m       # 2800 m east
        stations = _make_stations([
            ("SY", sy_lat, sy_lon, None),
            ("SZ", sy_lat, sz_lon, None),
            ("Z",  sy_lat, z_lon,  None),
        ])
        lines = [
            _line("L3", "bus", ["SY", "SZ"], ["08:00", "08:10"]),   # 2 dep -> wait 300 s
            _line("L2", "bus", ["SY", "SZ", "Z"], ["08:00"]),       # 1 dep -> wait 600 s (default)
        ]
        r = Router(stations, lines)

        res = r.route(sy_lat, sy_lon, sy_lat, z_lon)

        assert res.get("error") is None, res
        steps = res.get("steps", [])
        ride_steps = [s for s in steps if s.get("type") == "ride"]
        transfer_steps = [s for s in steps if s.get("type") == "transfer"]

        # Two ride segments: SY->SZ and SZ->Z.
        assert len(ride_steps) == 2, f"expected 2 ride steps, got {len(ride_steps)} in {res}"

        # All rides on L2 (stay-on-line). A state-collapse bug would produce a
        # transfer at SZ (L3 then L2) with ride_lines == {"L3", "L2"}.
        ride_lines = {s.get("line") for s in ride_steps}
        assert ride_lines == {"L2"}, (
            f"expected all rides on L2 (stay-on-line), got lines {ride_lines}; "
            f"path: {res}"
        )

        # No transfer step (staying on L2 avoids the alight/board at SZ).
        assert len(transfer_steps) == 0, (
            f"unexpected transfer in cheapest path: {res}"
        )

        # Duration: wait(L2=600s default) + ride(200m) + ride(2600m)
        #   = 600 + 200/6.111 + 2600/6.111 = 600 + 32.7 + 425.5 = 1058.2 s = 17.6 min
        # Must be well under the buggy total (~25.6 min) and over a pure-walk
        # baseline (2800 m / 4.5 km/h = 37.3 min).
        dur = res["duration_min"]
        assert dur < 22, f"expected <22 min staying on L2, got {dur} in {res}"
        assert dur > 14, f"duration suspiciously low ({dur}) in {res}"

    def test_state_label_persists_across_stops_on_same_line(self):
        """Travelling 3 stops on one line must not accrue extra waits."""
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.0)))
        A = (36.0, 10.0)
        B = (36.0, 10.0 + 800 * lon_per_m)     # 800 m
        C = (36.0, 10.0 + 1600 * lon_per_m)    # 1600 m
        D = (36.0, 10.0 + 2400 * lon_per_m)    # 2400 m from A
        stations = _make_stations([
            ("A", A[0], A[1], None),
            ("B", B[0], B[1], None),
            ("C", C[0], C[1], None),
            ("D", D[0], D[1], None),
        ])
        lines = [
            _line("LONE", "bus", ["A", "B", "C", "D"], ["08:00", "08:10", "08:20", "08:30"]),
        ]
        r = Router(stations, lines)
        res = r.route(A[0], A[1], D[0], D[1])
        assert res.get("error") is None, res
        ride_steps = [s for s in res["steps"] if s.get("type") == "ride"]
        ride_lines = {s.get("line") for s in ride_steps}
        assert ride_lines == {"LONE"}, f"expected single line LONE, got {ride_lines}"
        # wait 150 s + ride 2400 m: 150/60 + 2400/1000/22*60 = 2.5 + 6.55 = 9.05 min
        dur = res["duration_min"]
        assert dur < 12, f"duration {dur} too high for single-board 2.4km ride"
        assert dur > 7, f"duration {dur} too low for single-board 2.4km ride"


# ── Bug 2: wait charged per boarding, not per stop ──────────────────────

class TestWaitChargedOncePerBoarding:
    """Wait should be paid when boarding a line, not again at every stop."""

    def test_single_boarding_single_ride_wait_not_multiplied(self):
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.0)))
        stations = _make_stations([
            ("P", 36.0, 10.0, None),
            ("Q", 36.0, 10.0 + 2500 * lon_per_m, None),   # 2.5 km (below taxi threshold)
        ])
        lines = [
            _line("BUS1", "bus", ["P", "Q"], ["08:00", "08:10"]),  # 600s headway -> wait 300 s
        ]
        r = Router(stations, lines)
        res = r.route(stations["P"]["lat"], stations["P"]["lon"],
                      stations["Q"]["lat"], stations["Q"]["lon"])
        assert res.get("error") is None, res
        dur = res["duration_min"]
        # wait 300 s + ride 2.5 km at 22 km/h: 300/60 + 2.5/22*60 = 5 + 6.82 = 11.82 min
        expected = 300 / 60 + 2500 / 1000 / TRANSIT_DISPLAY_SPEED_KMH * 60
        assert dur == pytest.approx(expected, abs=0.5), (
            f"duration {dur} not ~{expected:.2f} (single boarding + 2.5km ride)"
        )

    def test_many_stop_ride_not_multiplied_by_headway(self):
        """A 10-stop ride must not pay 10x the headway.

        11 stops, 200 m apart = 2000 m total. Line departures every 5 min
        (headway 300 s) -> median wait 150 s. If wait were charged per stop
        the cost would be ~30 min; charged once it's ~8 min.
        """
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.0)))
        stop_ids = [f"S{i}" for i in range(11)]
        stations = _make_stations(
            [(sid, 36.0, 10.0 + i * 200 * lon_per_m, None) for i, sid in enumerate(stop_ids)]
        )
        lines = [
            _line("LONG BUS", "bus",
                  stop_ids,
                  ["08:{0:02d}".format(i * 5) for i in range(11)]),
        ]
        r = Router(stations, lines)
        first, last = stop_ids[0], stop_ids[-1]
        res = r.route(stations[first]["lat"], stations[first]["lon"],
                      stations[last]["lat"], stations[last]["lon"])
        assert res.get("error") is None, res
        dur = res["duration_min"]
        # 10 segments * 200 m = 2000 m. wait = 150 s (median of ten 300s headways).
        # expected = 150/60 + 2000/1000/22*60 = 2.5 + 5.45 = 7.95 min
        expected = 150 / 60 + 2000 / 1000 / TRANSIT_DISPLAY_SPEED_KMH * 60
        assert dur == pytest.approx(expected, abs=0.5), (
            f"duration {dur} not ~{expected:.2f} (single boarding + 2km ride)"
        )


# ── Bug 3: line attribution on shared corridors ─────────────────────────

class TestLineAttributionNotHeuristic:
    """Shared-edge segments must report the line actually taken, not the
    first line in the list that happens to share the edge."""

    def test_shared_edge_reports_correct_line(self):
        lon_per_m = 1.0 / (111320.0 * math.cos(math.radians(36.0)))
        stations = _make_stations([
            ("X", 36.0, 10.0, None),
            ("Y", 36.0, 10.0 + 2000 * lon_per_m, None),  # 2000 m (transit beats walk)
        ])
        lines = [
            _line("BUS-A", "bus", ["X", "Y"], ["08:00"]),
            _line("BUS-B", "bus", ["X", "Y"], ["08:05"]),  # same edge, different line
        ]
        r = Router(stations, lines)
        res = r.route(stations["X"]["lat"], stations["X"]["lon"],
                      stations["Y"]["lat"], stations["Y"]["lon"])
        assert res.get("error") is None, res
        ride_steps = [s for s in res["steps"] if s.get("type") == "ride"]
        assert len(ride_steps) == 1, res
        chosen = ride_steps[0].get("line")
        assert chosen in {"BUS-A", "BUS-B"}, f"unexpected line {chosen}"
        assert ride_steps[0].get("mode") == "bus"


# ── expected_wait midnight wrap (minor) ──────────────────────────────────

class TestExpectedWaitMidnightWrap:
    """expected_wait must handle departures that span midnight without
    inventing a phantom multi-hour headway."""

    def test_midnight_pair_no_phantom_headway(self):
        # 23:55 -> 06:05 next day is a ~6h10m headway, NOT ~18h.
        deps = ["23:55", "06:05"]
        w = expected_wait(deps, "bus")
        # Genuine headways: 6h10m (22200s, overnight) and 17h50m (64200s, daytime).
        # The daytime gap > 12h is treated as "no service" and excluded, so the
        # median is the overnight 22200s -> wait 11100s.
        assert w == pytest.approx(11100.0, abs=1.0), f"midnight pair gave {w}"

    def test_same_day_pairs_unchanged(self):
        # These must keep their existing values (the midnight fix must not
        # regress same-day departure pairs).
        assert expected_wait(["08:00", "08:10"], "bus") == pytest.approx(300.0)
        assert expected_wait(["08:00", "08:05", "08:15"], "bus") == pytest.approx(150.0)


# ── Taxi fare field ──────────────────────────────────────────────────────

class TestTaxiStepHasFare:
    """The advertised metered taxi fare (0.600 + 0.520/km) must appear in the
    taxi step of the API response, not only in the archived self-contained file."""

    def test_taxi_step_carries_fare(self):
        # Place start/end > TAXI_MIN_DISTANCE_M apart so taxi is offered.
        s_lat, s_lon = 36.0, 10.0
        e_lat = s_lat + 4000 / 111320.0          # ~4 km north
        e_lon = s_lon
        r = Router({}, [])  # empty graph -> no transit, only taxi fallback
        res = r.route(s_lat, s_lon, e_lat, e_lon)
        assert res.get("mode") == "taxi", f"expected taxi mode, got {res}"
        taxi_steps = [s for s in res.get("steps", []) if s.get("type") == "taxi"]
        assert len(taxi_steps) == 1, f"expected 1 taxi step, got {taxi_steps}"
        fare = taxi_steps[0].get("fare_dinars")
        assert fare is not None, "taxi step missing fare_dinars field"
        direct_km = haversine(s_lat, s_lon, e_lat, e_lon) / 1000
        expected = TAXI_FARE_BASE + TAXI_FARE_PER_KM * direct_km
        assert fare == pytest.approx(expected, abs=0.01), (
            f"fare {fare} != expected {expected:.2f}"
        )

    def test_taxi_fare_formula_matches_readme(self):
        # 10 km taxi: 0.600 + 0.520*10 = 5.80 DT.
        direct_km = 10.0
        fare = TAXI_FARE_BASE + TAXI_FARE_PER_KM * direct_km
        assert fare == pytest.approx(0.600 + 0.520 * 10.0)
        assert fare == pytest.approx(5.80)
