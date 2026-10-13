"""Guards for mode restriction and the no-straight-line rule.

Two properties are asserted here, and both are the kind that regress silently:

1. Every itinerary respects the mode set it was searched with. Showing a
   train journey for a bus-only request is the failure this prevents.

2. A leg long enough for its absence to be visible is never handed to the
   client with an empty polyline and no warning. That combination is exactly
   what makes a map draw a straight line across open country.
"""
from __future__ import annotations

import pytest

from bledi_transit.application.routing.router import build_graph
from bledi_transit.domain.modes import BUS_MODES, RAIL_MODES, TAXI_MODES
from bledi_transit.domain.tunables import GEOMETRY_REQUIRED_M

TUNIS = (36.8065, 10.1815)
SFAX = (34.7406, 10.7603)


@pytest.fixture(scope="module")
def router():
    return build_graph()[1]


def _ride_modes(result):
    return {s.get("mode") for s in result.get("steps", []) if s.get("type") == "ride"}


class TestSelectionsRestrictTheSearch:
    @pytest.mark.parametrize(
        "allowed", [BUS_MODES, RAIL_MODES, BUS_MODES | RAIL_MODES], ids=["bus", "rail", "bus+rail"]
    )
    def test_result_uses_only_selected_modes(self, router, allowed):
        res = router.route(*TUNIS, *SFAX, allowed_modes=allowed)
        modes = _ride_modes(res)
        allowed_ride = {m for m in modes if m != "walk"}
        assert allowed_ride <= allowed, (
            f"selection {sorted(allowed)} produced {sorted(allowed_ride - allowed)}"
        )

    def test_louaj_selection_yields_a_car_leg_only(self, router):
        res = router.route(*TUNIS, *SFAX, allowed_modes=TAXI_MODES)
        steps = res.get("steps", [])
        assert steps
        assert all(s.get("type") == "taxi" for s in steps)

    def test_combination_search_can_use_bus_and_train_together(self, router):
        """A multi-modal path is NOT reachable by searching one mode set alone.

        This is the guard on the guard: if the seed ever loses the ability to
        produce a bus+train path, the combination search degrades to a
        single-mode answer and the per-selection tests would still pass.
        """
        res = router.route(*TUNIS, *SFAX, allowed_modes=BUS_MODES | RAIL_MODES)
        modes = _ride_modes(res) - {"walk"}
        assert len(modes) >= 2, f"expected a mixed bus+train path, got {modes}"


class TestNoStraightLinesForVisibleLegs:
    def test_flagged_edge_property_matches_the_threshold(self, router):
        """needs_geometry must be false only when the gap is genuinely invisible."""
        checked = 0
        for edges in router.adj.values():
            for e in edges:
                if e.mode == "walk" or e.geometry:
                    continue
                checked += 1
                assert e.needs_geometry == (e.straight_m >= GEOMETRY_REQUIRED_M)
        assert checked, "no geometry-less transit edge was exercised"

    def test_a_flagged_ride_step_reports_needs_geometry(self, router):
        res = router.route(*TUNIS, *SFAX)
        flagged = [
            s for s in res.get("steps", [])
            if s.get("type") == "ride"
            and not s.get("geometry")
            and (s.get("straight_m") or 0) >= GEOMETRY_REQUIRED_M
        ]
        for s in flagged:
            assert s.get("needs_geometry") is True, (
                f"{s.get('from_name')} -> {s.get('to_name')} is "
                f"{s.get('straight_m')} m with no polyline but is not flagged"
            )

    def test_short_geometry_less_legs_are_not_flagged(self, router):
        """A 40 m hop drawn straight is invisible and must stay allowed.

        Flagging everything would make the whole map undrawable over 262 short
        edges that no user can tell apart from a straight line.
        """
        short = [
            e
            for edges in router.adj.values()
            for e in edges
            if e.mode != "walk" and not e.geometry and e.straight_m < GEOMETRY_REQUIRED_M
        ]
        assert short, "expected some short geometry-less edges"
        assert not any(e.needs_geometry for e in short)


class TestSeedDataQualityIsVisible:
    def test_seed_has_implausible_consecutive_stops(self):
        """Documents WHY flagged legs exist rather than pretending they cannot.

        The SNCFT train lines are not stop sequences: train_24_sncft lists
        tozeur then borj_cedria as consecutive stops, 370.7 km apart. No rail
        geometry can match that, so those edges are permanently unmatchable and
        the only honest rendering is "no path here".

        If this test starts failing, the seed was fixed and the geometry gaps
        above should shrink -- that is a good day, and this assertion is the
        reminder to re-run the geometry build.
        """
        from bledi_transit.application.routing.router import build_graph as _bg

        graph, router = _bg()
        implausible = [
            (sid, e) for sid, edges in router.adj.items() for e in edges
            if e.mode == "train" and not e.geometry and e.straight_m > 100_000
        ]
        assert implausible, (
            "no long unmatchable train edges remain -- the seed may have been "
            "repaired; re-run build_route_geometry.py to fill the gaps"
        )


class TestApiNeverFallsBackToAStraightLine:
    """End-to-end: the HTTP envelope must not hand back a drawable-looking
    two-point path for a leg the router flagged.

    An earlier mutation -- restoring the unconditional `_geometry_for()`
    fallback in main.py -- passed the whole suite, because that fallback happens
    to return [] for these legs today. This asserts the invariant directly so it
    cannot pass for the wrong reason again.
    """

    def test_flagged_leg_never_yields_a_geometry_looking_leg(self, router):
        """Invariant: a leg flagged needs_geometry must never carry a polyline.

        This used to assert `flagged` was non-empty and failed with
        "the test is vacuous" once real rail-track geometry landed -- there are
        no longer any geometry-less ride legs on this trip. The invariant is
        still the thing worth protecting, so it is now asserted
        unconditionally over every ride leg, and the flag is also checked for
        self-consistency (needs_geometry exactly when there is no polyline).
        """
        res = router.route(*TUNIS, *SFAX)
        rides = [s for s in res.get("steps", []) if s.get("type") == "ride"]
        assert rides, "no ride legs at all; the trip should not be pure walk"

        for s in rides:
            has_geom = bool(s.get("geometry"))
            if s.get("needs_geometry"):
                assert not has_geom, "flagged leg must not carry a polyline"
            # needs_geometry must agree with reality, both ways.
            long_leg = (s.get("straight_m") or 0) >= GEOMETRY_REQUIRED_M
            assert bool(s.get("needs_geometry")) == (long_leg and not has_geom), (
                f"needs_geometry disagrees with geometry presence: {s.get('line')}"
            )

    def test_no_ride_leg_is_a_bare_straight_line(self, router):
        """Regression guard for the zigzag: a long ride must follow real track.

        Before rail-track geometry, rail legs with no cached segment rendered as
        two points joined by a straight line, which is what made the map appear
        to jump to the next station and come back.
        """
        res = router.route(*TUNIS, *SFAX)
        for s in res.get("steps", []):
            if s.get("type") != "ride":
                continue
            straight_m = s.get("straight_m") or 0
            if straight_m < GEOMETRY_REQUIRED_M:
                continue
            geom = s.get("geometry") or []
            assert len(geom) > 2, (
                f"long {s.get('mode')} leg on {s.get('line')} is a bare "
                f"{len(geom)}-point straight line over {straight_m} m"
            )

    def test_steps_helper_respects_the_flag(self):
        """The API conversion must not resurrect a straight line for a flagged step."""
        from bledi_transit.main import _steps_to_legs

        flagged_step = {
            "type": "ride", "mode": "train", "line": "train_24_sncft",
            "start": [36.8065, 10.1815], "end": [34.7406, 10.7603],
            "from_name": "A", "to_name": "B", "from_id": "a", "to_id": "b",
            "geometry": [], "needs_geometry": True,
            "distance_m": 235576, "straight_m": 235576, "time_seconds": 12000.0,
        }
        legs = _steps_to_legs([flagged_step])
        assert len(legs) == 1
        leg = legs[0]
        assert leg["has_geometry"] is False
        assert leg["needs_geometry"] is True, (
            "client cannot tell 'draw nothing' from 'draw a straight line' "
            "unless needs_geometry is set"
        )
        assert leg["geometry"] == []

    def test_unflagged_short_step_may_carry_geometry(self):
        """The normal case still works: an unflagged step is drawable."""
        from bledi_transit.main import _steps_to_legs

        ok_step = {
            "type": "ride", "mode": "bus", "line": "bus_1",
            "start": [36.8065, 10.1815], "end": [36.8080, 10.1830],
            "from_name": "A", "to_name": "B", "from_id": "a", "to_id": "b",
            "geometry": [[36.8065, 10.1815], [36.8070, 10.1820], [36.8080, 10.1830]],
            "needs_geometry": False, "distance_m": 250, "time_seconds": 40.0,
        }
        leg = _steps_to_legs([ok_step])[0]
        assert leg["has_geometry"] is True
        assert leg["needs_geometry"] is False


class TestRouterToOptionSuppressesTheFallback:
    """The straight-line fallback in _router_to_option must be unreachable for a
    flagged leg.

    The earlier mutation of this branch passed the suite because the test drove
    _steps_to_legs(), which never calls _geometry_for(). These drive
    _router_to_option(), where the branch actually lives, using a station pair
    that genuinely HAS cached geometry -- so if the flag is ignored, the leg
    silently acquires a polyline (or would fall back to a straight one).
    """

    def test_flagged_leg_gets_no_geometry_even_when_the_pair_is_cached(self):
        from bledi_transit import main as M

        pair = next(
            (k for k, v in M._GEOMETRY.items() if v.get("geometry")), None
        )
        assert pair, "no cached geometry to test against"
        a_id, b_id = pair.split("|")
        step = {
            "type": "ride", "mode": "train", "line": "train_x",
            "from": {"lat": 36.8, "lon": 10.1}, "to": {"lat": 36.81, "lon": 10.11},
            "from_name": "A", "to_name": "B",
            "from_id": a_id, "to_id": b_id,
            "geometry": [], "needs_geometry": True,
            "distance_m": 1000, "straight_m": 1000, "time_seconds": 200.0,
        }
        out = M._router_to_option(
            {"mode": "transit", "duration_min": 5.0, "steps": [step]}
        )
        s = out["steps"][0]
        assert s["has_geometry"] is False, (
            "a flagged leg acquired geometry from the station cache; the map "
            "would then draw a path the router never verified"
        )
        assert s["geometry"] == []
        assert s["needs_geometry"] is True

    def test_unflagged_leg_does_use_the_cached_geometry(self):
        """The complementary case: without the flag the cache is still used.

        Guards against 'fixing' the false line by deleting the fallback, which
        would leave every unflagged leg drawn straight too.
        """
        from bledi_transit import main as M

        pair = next(k for k, v in M._GEOMETRY.items() if v.get("geometry"))
        a_id, b_id = pair.split("|")
        step = {
            "type": "ride", "mode": "train", "line": "train_x",
            "from": {"lat": 36.8, "lon": 10.1}, "to": {"lat": 36.81, "lon": 10.11},
            "from_name": "A", "to_name": "B",
            "from_id": a_id, "to_id": b_id,
            "geometry": [], "needs_geometry": False,
            "distance_m": 1000, "straight_m": 1000, "time_seconds": 200.0,
        }
        out = M._router_to_option(
            {"mode": "transit", "duration_min": 5.0, "steps": [step]}
        )
        s = out["steps"][0]
        assert s["has_geometry"] is True
        assert len(s["geometry"]) >= 2


class TestMergeBreaksOnARealGap:
    """A hole in the ride must not be stitched over.

    Concatenating a real polyline onto an unmatchable one produces a single
    discontinuous line that jumps across open country. Measured on Tunis->Sfax:
    93 km of polyline for a 214 km journey, because the 125 km Borj Cedria ->
    Sidi Bou Goubrine seed gap has no rail geometry.
    """

    @staticmethod
    def _ride(name, frm, to, geom, needs, f_id="a", t_id="b"):
        return {
            "type": "ride", "mode": "train", "line": "L",
            "start": frm, "end": to, "from_name": name[0], "to_name": name[1],
            "from_id": f_id, "to_id": t_id, "geometry": geom,
            "needs_geometry": needs, "distance_m": 1000,
            "straight_m": 1000, "time_seconds": 100.0,
        }

    def test_gap_first_then_real_stays_two_legs(self):
        from bledi_transit.main import _steps_to_legs

        steps = [
            self._ride(("GAP_FROM", "GAP_TO"), [36.0, 10.0], [35.9, 10.1], [], True),
            self._ride(("GAP_TO", "REAL_END"), [35.9, 10.1], [35.8, 10.2],
                       [[35.9, 10.1], [35.85, 10.15], [35.8, 10.2]], False),
        ]
        legs = _steps_to_legs(steps)
        assert len(legs) == 2, f"gap was stitched over: {len(legs)} leg(s)"
        assert legs[0]["needs_geometry"] is True
        assert legs[0]["geometry"] == []
        assert legs[1]["breaks_continuity"] is True

    def test_contiguous_ride_still_merges(self):
        """The complementary case: no gap means one leg, as before."""
        from bledi_transit.main import _steps_to_legs

        steps = [
            self._ride(("A", "B"), [35.9, 10.1], [35.8, 10.2],
                       [[35.9, 10.1], [35.85, 10.15], [35.8, 10.2]], False),
            self._ride(("B", "C"), [35.8, 10.2], [35.7, 10.3],
                       [[35.8, 10.2], [35.75, 10.25], [35.7, 10.3]], False),
        ]
        legs = _steps_to_legs(steps)
        assert len(legs) == 1
        assert len(legs[0]["geometry"]) == 6

    def test_gap_in_the_middle_yields_three_legs(self):
        from bledi_transit.main import _steps_to_legs

        steps = [
            self._ride(("A", "B"), [35.9, 10.1], [35.8, 10.2],
                       [[35.9, 10.1], [35.85, 10.15], [35.8, 10.2]], False),
            self._ride(("B", "GAP2"), [35.8, 10.2], [35.9, 10.1], [], True),
            self._ride(("GAP2", "D"), [35.9, 10.1], [35.7, 10.3],
                       [[35.9, 10.1], [35.8, 10.2], [35.7, 10.3]], False),
        ]
        legs = _steps_to_legs(steps)
        assert len(legs) == 3
        assert sum(1 for l in legs if l["needs_geometry"]) == 1
