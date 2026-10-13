"""Regression guards for the three-transport-option routing.

Each option must be its OWN mode-restricted search, not a slice of one combined
answer. A combined search minimises total time and will return a train when the
user asked for a bus, so deriving options from it produces confidently wrong
cards -- the option labelled "Bus" containing a train.

These assert on Router.route(allowed_modes=...) directly, i.e. on the search the
endpoint actually performs, rather than on the HTTP envelope.
"""
from __future__ import annotations

import pytest

from bledi_transit.application.routing.router import build_graph
from bledi_transit.domain.geo import polyline_length
from bledi_transit.domain.modes import BUS_MODES, RAIL_MODES, TAXI_MODES

# Tunis -> Sfax: a trip with real rail, but NO buses (only trains).
# Use a destination that IS reachable by bus for the bus option test.
# sidi_salah is the southernmost bus stop (lat 34.858), ~223 km from Tunis.
TUNIS = (36.8065, 10.1815)
SFAX = (34.7406, 10.7603)  # rail/taxi only
SIDI_SALAH = (34.8580193, 10.7673434)  # reachable by bus


@pytest.fixture(scope="module")
def router():
    _graph, r = build_graph()
    return r


def _ride_modes(result):
    return {s.get("mode") for s in result.get("steps", []) if s.get("type") == "ride"}


class TestOptionModeFamilies:
    def test_families_do_not_overlap(self):
        assert not (BUS_MODES & RAIL_MODES)
        assert not (BUS_MODES & TAXI_MODES)
        assert not (RAIL_MODES & TAXI_MODES)


class TestOptionsAreSeparatelyComputed:
    def test_bus_option_contains_only_bus_family_rides(self, router):
        # Use a destination that actually has bus service (sidi_salah)
        res = router.route(*TUNIS, *SIDI_SALAH, allowed_modes=BUS_MODES)
        modes = _ride_modes(res)
        assert modes, "bus option produced no ride at all"
        assert modes <= BUS_MODES, f"bus option leaked other modes: {modes - BUS_MODES}"

    def test_train_option_contains_only_rail_family_rides(self, router):
        # Sfax has rail service
        res = router.route(*TUNIS, *SFAX, allowed_modes=RAIL_MODES)
        modes = _ride_modes(res)
        assert modes, "train option produced no ride at all"
        assert modes <= RAIL_MODES, f"train option leaked: {modes - RAIL_MODES}"

    def test_louaj_option_is_a_single_direct_car_leg(self, router):
        """A louaj leg has no timetable and does not chain stops.

        If the restricted search returns a multi-leg transit path it is not a
        louaj answer, and the card labelled "Louaj / Taxi" would be a lie.
        """
        res = router.route(*TUNIS, *SFAX, allowed_modes=TAXI_MODES)
        steps = res.get("steps", [])
        assert steps
        assert res.get("mode") == "taxi", f"louaj option returned {res.get('mode')}"
        assert all(s.get("type") == "taxi" for s in steps), (
            "louaj option is not a single direct car leg"
        )

    def test_unrestricted_search_may_mix_families(self, router):
        """The guard on the guard: allowed_modes=None must NOT be restrictive.

        If this fails the other three tests are passing for the wrong reason --
        e.g. the seed simply having no bus service on this corridor.
        """
        res = router.route(*TUNIS, *SFAX)
        modes = _ride_modes(res)
        assert len(modes) > 1, (
            f"unrestricted search returned only {modes}; the per-option tests "
            "would pass vacuously"
        )


class TestOptionEdgesCarryRealMetrics:
    def test_ride_steps_expose_distance_and_geometry_fields(self, router):
        # Train to Sfax
        res = router.route(*TUNIS, *SFAX, allowed_modes=RAIL_MODES)
        rides = [s for s in res.get("steps", []) if s.get("type") == "ride"]
        assert rides, "train option has no ride steps"
        for s in rides:
            assert s.get("distance_m") is not None
            assert s.get("time_seconds") is not None
            assert s.get("geometry") is not None, (
                "step must carry a geometry key (possibly empty) so the "
                "client can tell 'no path' from 'straight line'"
            )

        # Bus to sidi_salah (which has bus service)
        res = router.route(*TUNIS, *SIDI_SALAH, allowed_modes=BUS_MODES)
        rides = [s for s in res.get("steps", []) if s.get("type") == "ride"]
        assert rides, "bus option has no ride steps"
        for s in rides:
            assert s.get("distance_m") is not None
            assert s.get("time_seconds") is not None
            assert s.get("geometry") is not None, (
                "step must carry a geometry key (possibly empty) so the "
                "client can tell 'no path' from 'straight line'"
            )

    def test_geometry_is_never_shorter_than_the_straight_line(self, router):
        """A path along a network cannot undercut the crow-flies distance.

        A shorter value means a mis-oriented or mis-stitched polyline, which
        draws a line that does not follow the infrastructure at all.
        """
        checked = 0
        for key, allowed in (("bus", BUS_MODES), ("train", RAIL_MODES)):
            res = router.route(*TUNIS, *SFAX, allowed_modes=allowed)
            for s in res.get("steps", []):
                geom = s.get("geometry") or []
                if len(geom) < 2:
                    continue
                straight = s.get("straight_m")
                if not straight:
                    continue
                assert polyline_length(geom) >= 0.95 * straight, (
                    f"{key} leg {s.get('from_name')}->{s.get('to_name')} has a "
                    f"polyline shorter than the straight line"
                )
                checked += 1
        assert checked, "no cached geometry was exercised at all"


class TestWalkEdgesAlwaysPermitted:
    def test_walk_survives_a_rail_only_restriction(self, router):
        """Every option starts and ends on foot.

        A restriction that blocked walking would make a rail-only trip
        unreachable from any origin that is not itself a station, which is the
        "router only answers for stops" failure mode.
        """
        res = router.route(*TUNIS, *SFAX, allowed_modes=RAIL_MODES)
        assert res.get("steps"), "rail-only search returned nothing"
        first = res["steps"][0]
        assert first.get("type") == "walk", (
            f"first step should be the access walk, got {first.get('type')}"
        )

    def test_rail_only_search_uses_no_bus_edges(self, router):
        res = router.route(*TUNIS, *SFAX, allowed_modes=RAIL_MODES)
        for e in res.get("_edges", []) or []:
            assert e.mode in RAIL_MODES or e.mode == "walk"
