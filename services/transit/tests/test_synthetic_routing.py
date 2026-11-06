"""Routing regressions on a tiny synthetic network: no seed, no road graph needed.

Each test pins one defect found in the real responses (see FINDINGS.md).
"""
from __future__ import annotations

import math

from bledi_transit.application.routing.router import Router
from bledi_transit.domain.geo import haversine_m, polyline_length
from bledi_transit.domain.modes import resolve_allowed_modes

LON_STEP = 0.009  # ~800 m at Tunis latitude


def _st(stations, sid, lat, lon, mode):
    stations[sid] = {"id": sid, "name": sid.upper(), "lat": lat, "lon": lon, "mode": mode}


def make_router(paths=None) -> Router:
    stations: dict = {}
    # A TGM-like metro line: 14 stations ~800 m apart, so walk edges (<= 900 m) join neighbours.
    for i in range(14):
        _st(stations, f"m{i}", 36.80, 10.19 + LON_STEP * i, "metro")
    # An intercity louage pair ~230 km apart, and an intercity bus pair ~20 km apart.
    _st(stations, "l0", 36.80, 10.18, "louage")
    _st(stations, "l1", 34.74, 10.76, "louage")
    _st(stations, "b0", 36.60, 10.30, "bus")
    _st(stations, "b1", 36.60, 10.55, "bus")
    lines = [
        # Sparse published departures: the median headway is huge, so the wait hits its cap.
        {"id": "metro_x", "mode": "metro", "stations": [f"m{i}" for i in range(14)], "departures": ["05:00", "23:00"]},
        {"id": "louage_x", "mode": "louage", "stations": ["l0", "l1"]},
        {"id": "bus_x", "mode": "bus", "stations": ["b0", "b1"]},
    ]
    return Router(stations, lines, segments={}, walk_segments={}, taxi_segments={}, paths=paths)


def _walks(steps):
    return [s for s in steps if s.get("type") == "walk"]


def _kmh(step) -> float:
    ride_min = step["duration_min"] - (step.get("wait_min") or 0.0)
    return step["distance_m"] / 1000.0 / (ride_min / 60.0)


class TestNoWalkingAlongATransitLine:
    def test_train_only_never_walks_the_metro_line(self):
        r = make_router()
        out = r.route_plan(36.80, 10.19 - 0.0005, 36.80, 10.19 + LON_STEP * 13 + 0.0005)
        assert out["itineraries"], "the metro itself must still be offered"
        for it in out["itineraries"]:
            walk_m = sum(s["distance_m"] for s in _walks(it["legs"]))
            assert walk_m <= 5000, f"{it['label']}: {walk_m} m of walking"
            assert any(s["type"] in ("ride", "taxi", "louaj") for s in it["legs"]), f"{it['label']} has no vehicle at all"

    def test_no_two_walks_in_a_row(self):
        r = make_router()
        out = r.route_plan(36.80, 10.19 - 0.0005, 36.80, 10.19 + LON_STEP * 13 + 0.0005)
        for it in out["itineraries"]:
            kinds = [s["type"] for s in it["legs"]]
            assert not any(a == b == "walk" for a, b in zip(kinds, kinds[1:])), kinds


class TestBannedWalkEdges:
    def test_a_banned_transfer_walk_is_never_used(self):
        stations: dict = {}
        _st(stations, "a0", 36.50, 10.00, "bus")
        _st(stations, "a1", 36.50, 10.10, "bus")
        _st(stations, "b0", 36.50, 10.1065, "bus")  # ~600 m from a1: a walk transfer
        _st(stations, "b1", 36.50, 10.20, "bus")
        lines = [
            {"id": "bus_a", "mode": "bus", "stations": ["a0", "a1"]},
            {"id": "bus_b", "mode": "bus", "stations": ["b0", "b1"]},
        ]
        r = Router(stations, lines, segments={}, walk_segments={}, taxi_segments={}, paths=None)
        allowed = resolve_allowed_modes(["bus"], None)
        ok = r.route(36.50, 9.9995, 36.50, 10.2005, allowed_modes=allowed)
        assert any(s["type"] == "walk" and s.get("from_id") == "a1" for s in ok["steps"]), ok
        banned = r.route(36.50, 9.9995, 36.50, 10.2005, allowed_modes=allowed,
                         banned_walks=frozenset({("a1", "b0"), ("b0", "a1")}))
        assert not any(s.get("from_id") == "a1" and s.get("to_id") == "b0" for s in banned["steps"]), banned


class TestLouageOnlyRunsOnItsLines:
    """Louage is not point-to-point: it exists only as a ride on a louage line."""

    def test_louage_is_offered_where_a_line_runs(self):
        r = make_router()
        out = r.route_plan(36.80, 10.1801, 34.74, 10.7601)
        modes = [m for it in out["itineraries"] for m in it["modes_used"]]
        assert "louaj" in modes, [it["label"] for it in out["itineraries"]]

    def test_no_louage_between_two_points_that_no_line_connects(self):
        r = make_router()
        # ~60 km apart, near no louage stand: only a taxi may answer, never a "direct louage"
        out = r.route_plan(36.20, 9.00, 36.20, 9.60)
        for it in out["itineraries"]:
            assert "louaj" not in it["modes_used"], it["label"]
            assert all(s["type"] != "louaj" for s in it["legs"]), it["label"]

    def test_direct_road_option_is_a_taxi_and_stops_at_150_km(self):
        r = make_router()
        near = r.route_plan(36.20, 9.00, 36.20, 9.20)  # ~18 km
        assert any("taxi" in it["modes_used"] for it in near["itineraries"]), near
        far = r.route_plan(36.20, 9.00, 34.60, 9.60)   # ~190 km
        assert not any("taxi" in it["modes_used"] for it in far["itineraries"]), far

    def test_louage_only_search_never_returns_a_taxi(self):
        r = make_router()
        res = r.route(36.20, 9.00, 36.20, 9.20, allowed_modes=resolve_allowed_modes(["louaj"], None))
        assert not res.get("steps"), res


class TestBoardingInTheMiddleOfACorridor:
    """Tebourba-Mateur: no louage between them, but Bab Saadoun-Mateur passes Djedeida."""

    def _router(self):
        stations: dict = {}
        _st(stations, "hub", 36.81, 10.16, "louage")
        _st(stations, "mid", 36.85, 9.93, "louage")      # the town in the middle (Djedeida)
        _st(stations, "end", 37.04, 9.67, "louage")
        _st(stations, "feeder", 36.83, 9.84, "bus")       # where the rider starts (Tebourba)
        lines = [
            {"id": "corridor_x", "mode": "louage", "stations": ["hub", "mid", "end"], "wait_s": 900.0},
            {"id": "bus_feeder", "mode": "bus", "stations": ["feeder", "mid"]},
        ]
        return Router(stations, lines, segments={}, walk_segments={}, taxi_segments={}, paths=None)

    def test_rider_boards_the_corridor_at_the_intermediate_stop(self):
        r = self._router()
        res = r.route(36.8301, 9.8401, 37.0401, 9.6701)
        rides = [(s["line"], s["from_id"], s["to_id"]) for s in res["steps"] if s["type"] == "ride"]
        assert ("bus_feeder", "feeder", "mid") in rides, rides
        assert any(l == "corridor_x" and f == "mid" and t == "end" for l, f, t in rides), rides

    def test_corridor_is_usable_in_both_directions(self):
        r = self._router()
        res = r.route(37.0401, 9.6701, 36.8501, 9.9301, allowed_modes=resolve_allowed_modes(["louaj"], None))
        assert any(s["type"] == "ride" and s["from_id"] == "end" and s["to_id"] == "mid" for s in res["steps"]), res

    def test_line_can_state_its_own_boarding_wait(self):
        assert self._router().line_wait["corridor_x"] == 900.0


class TestBusSearchDoesNotWalkAcrossTheCountry:
    def test_no_bus_stop_nearby_means_no_bus_option(self):
        r = make_router()
        allowed = resolve_allowed_modes(["bus"], None)
        # 22 km south of the nearest bus stop
        res = r.route(36.40, 10.30, 36.60, 10.55, allowed_modes=allowed)
        assert not any(s.get("distance_m", 0) > 3000 for s in _walks(res.get("steps") or [])), res


class TestSpeeds:
    def test_louage_runs_at_road_speed_not_bus_speed(self):
        r = make_router()
        allowed = resolve_allowed_modes(["louaj"], None)
        res = r.route(36.80, 10.1801, 34.74, 10.7601, allowed_modes=allowed)
        rides = [s for s in res["steps"] if s["type"] == "ride"]
        assert rides, res
        assert 60 <= _kmh(rides[0]) <= 90, _kmh(rides[0])

    def test_intercity_bus_hop_is_not_timed_like_a_city_hop(self):
        r = make_router()
        allowed = resolve_allowed_modes(["bus"], None)
        res = r.route(36.6001, 10.30, 36.6001, 10.55, allowed_modes=allowed)
        rides = [s for s in res["steps"] if s["type"] == "ride"]
        assert rides, res
        assert _kmh(rides[0]) >= 45, _kmh(rides[0])

    def test_urban_rail_wait_is_capped(self):
        r = make_router()
        assert r.line_wait["metro_x"] <= 7 * 60


class _StubPaths:
    """A road graph whose answer is 30% longer than the straight line."""

    def road(self, a_lat, a_lon, b_lat, b_lon, mode):
        bump = 0.35 * max(abs(b_lat - a_lat), abs(b_lon - a_lon))  # a 25-35% detour
        mid = [(a_lat + b_lat) / 2 + bump, (a_lon + b_lon) / 2]
        geom = [[a_lat, a_lon], mid, [b_lat, b_lon]]
        return geom, polyline_length(geom)

    def rail(self, *a):
        return None

    def foot_bridges(self, *a):
        return []


class TestReportedDistanceMatchesTheDrawnLine:
    def test_louage_leg_distance_is_the_road_not_the_straight_line(self):
        r = make_router(paths=_StubPaths())
        allowed = resolve_allowed_modes(["louaj"], None)
        res = r.route(36.80, 10.1801, 34.74, 10.7601, allowed_modes=allowed)
        ride = next(s for s in res["steps"] if s["type"] == "ride")
        drawn = polyline_length(ride["geometry"])
        assert abs(ride["distance_m"] - drawn) <= 0.01 * drawn, (ride["distance_m"], drawn)
