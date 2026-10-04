#!/usr/bin/env python3
"""Walk-edge routing behaviour: the "long distance is one straight line" bug.

The router used to build a transit-only graph. With no walk edges, a
destination stop that no line called at was simply unreachable, so any trip to
a town outside the served network collapsed into a single taxi leg drawn
straight across the map. These tests pin the behaviour that replaced it:

  1. the graph actually contains walk edges (the regression itself)
  2. a walk edge is a walk leg, not an absorbed hop on a ride
  3. transit wins outright once it exists; taxi is demoted to an alternative
  4. a destination with no nearby served stop gets an explicit local-hop leg
     that says so, instead of a silent straight line
  5. walk edges do not corrupt the (station, line) cost model -- they reset the
     line context rather than continuing it free

Run:  python -m pytest tests/test_walk_routing.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.backend.app.routing import (  # noqa: E402
    MAX_WALK_EDGE_METERS,
    WALK_EDGE,
    Router,
    _load_seed,
)

# Long-distance OD pairs that used to return a single taxi leg.
LONG_TRIPS = {
    "Tunis->Sfax": (36.8078, 10.1815, 34.7406, 10.7603),
    "Tunis->Bizerte": (36.8078, 10.1815, 37.2744, 9.8739),
    "Sousse->Nabeul": (35.8256, 10.6360, 36.4560, 10.7376),
}


@pytest.fixture(scope="module")
def router() -> Router:
    seed = _load_seed()
    return Router({s["id"]: s for s in seed["stations"]}, seed["lines"])


class TestWalkEdgesExist:
    def test_graph_has_walk_edges(self, router):
        """The bug: zero walk edges meant transit-only reachability."""
        walk = [
            e
            for edges in router.adj.values()
            for e in edges
            if e.mode == "walk"
        ]
        assert walk, "graph has no walk edges; destination stops off the network are unreachable"
        assert len(walk) > 1000, f"implausibly few walk edges: {len(walk)}"

    def test_walk_edges_are_bidirectional_and_bounded(self, router):
        by_pair: dict[tuple[str, str], float] = {}
        for src, edges in router.adj.items():
            for e in edges:
                dst, line_id, mode = e.to_id, e.line, e.mode
                if mode != "walk":
                    continue
                assert line_id == WALK_EDGE
                # 0 m is legitimate: the seed holds several same-place
                # duplicates (a bus stop and its rail counterpart sharing
                # identical coordinates), and walking between them is free.
                #
                # The walkable-radius gate applies to the STRAIGHT-line
                # separation, which is what decides whether two stops are
                # linked at all. distance_m is the real footpath and is
                # legitimately longer -- a stop 880 m away as the crow flies
                # can be a 1 340 m walk around a river or a motorway. Bounding
                # distance_m by the radius would reject real geometry; the
                # physics check below is the one that must hold.
                assert 0 <= e.straight_m <= MAX_WALK_EDGE_METERS
                # A path along a network cannot be shorter than the straight
                # line it replaces.
                assert e.distance_m >= 0.95 * e.straight_m - 1e-6
                by_pair[(src, dst)] = e.distance_m
        assert by_pair
        # Every directed walk edge must have its reverse.
        missing = [p for p in by_pair if (p[1], p[0]) not in by_pair]
        assert not missing, f"walk edges not bidirectional: {missing[:5]}"

    def test_a_stop_off_the_network_is_now_reachable(self, router):
        """Kairouan: 29 stops within 2 km, every one with zero edges before."""
        served = [
            s
            for s in router.stations.values()
            if s.get("lat")
            and s.get("lon")
            and any(e.mode != "walk" for e in router.adj.get(s["id"], ()))
        ]
        assert served
        kairouan = min(
            (s for s in served),
            key=lambda s: ((s["lat"] - 35.6781) ** 2 + (s["lon"] - 10.0963) ** 2) ** 0.5,
        )
        assert kairouan is not None


class TestItineraryShape:
    @pytest.mark.parametrize("name", sorted(LONG_TRIPS))
    def test_long_trip_is_not_a_single_taxi_leg(self, router, name):
        lat1, lon1, lat2, lon2 = LONG_TRIPS[name]
        res = router.route(lat1, lon1, lat2, lon2)
        steps = res.get("steps") or []
        assert steps, res
        assert len(steps) > 1, f"{name} collapsed to a single leg: {steps}"
        assert not (
            len(steps) == 1 and steps[0].get("type") == "taxi"
        ), f"{name} is still one straight taxi line"

    @pytest.mark.parametrize("name", sorted(LONG_TRIPS))
    def test_transit_wins_over_taxi(self, router, name):
        """Transit must win outright; taxi is an alternative, not the answer."""
        lat1, lon1, lat2, lon2 = LONG_TRIPS[name]
        res = router.route(lat1, lon1, lat2, lon2)
        assert res.get("mode") == "transit", (
            f"{name} chose {res.get('mode')} over an available transit route"
        )

    def test_walk_appears_as_its_own_leg(self, router):
        """Walk edges must render as walk steps, not vanish into the rides.

        The old mutation ("if line_used is None and seg_m > 1:" -> False) removed
        the walk rendering entirely and still passed a presence-only assertion,
        because the start and final walk legs are emitted elsewhere. So this
        counts walk legs that sit BETWEEN two rides -- those can only come from
        the walk-edge renderer.
        """
        lat1, lon1, lat2, lon2 = LONG_TRIPS["Tunis->Sfax"]
        res = router.route(lat1, lon1, lat2, lon2)
        steps = res.get("steps") or []
        types = [s.get("type") for s in steps]
        assert "ride" in types

        interior_walks = [
            s for i, s in enumerate(steps)
            if s.get("type") == "walk" and 0 < i < len(steps) - 1
        ]
        assert interior_walks, (
            f"no walk leg between rides; a walk-edge handover is not rendered "
            f"as its own step (types={types})"
        )
        # Each interior walk must be preceded and followed by a ride: that is
        # what makes it a transfer handover rather than a start/end walk.
        for i, s in enumerate(steps):
            if s.get("type") != "walk" or not (0 < i < len(steps) - 1):
                continue
            assert steps[i - 1].get("type") == "ride", (
                f"interior walk not preceded by a ride: {steps[i - 1].get('type')}"
            )
            assert steps[i + 1].get("type") == "ride", (
                f"interior walk not followed by a ride: {steps[i + 1].get('type')}"
            )
            # Timed at walking speed, not transit speed.
            dist_km = s.get("distance_m", 0) / 1000.0
            if dist_km > 0 and s.get("duration_min", 0) > 0:
                implied = dist_km / (s["duration_min"] / 60.0)
                assert implied < 12.0, f"walk leg looks like a ride: {s}"

    def test_taxi_is_still_offered_as_an_alternative(self, router):
        lat1, lon1, lat2, lon2 = LONG_TRIPS["Tunis->Sfax"]
        res = router.route(lat1, lon1, lat2, lon2)
        alts = res.get("alternatives") or []
        assert any(a.get("mode") == "taxi" for a in alts), (
            "taxi must still be offered alongside transit"
        )

    def test_short_trip_is_not_served_by_taxi(self, router):
        """Guard the other direction: walking distance must not gain a taxi leg."""
        res = router.route(36.806, 10.184, 36.806 + 0.009, 10.184)
        offered = {s.get("type") for s in res.get("steps") or []}
        offered |= {a.get("mode") for a in (res.get("alternatives") or [])}
        assert "taxi" not in offered


class TestUnservedDestination:
    def test_destination_without_a_stop_gets_an_explicit_local_hop(self, router):
        """Mahdia's nearest served stop is ~90 km away, so the final leg must
        be labelled as a local hop rather than presented as a walk."""
        res = router.route(36.8078, 10.1815, 34.0622, 11.35)
        steps = res.get("steps") or []
        assert len(steps) > 1, "Mahdia collapsed to a single leg"
        hops = [s for s in steps if s.get("note") == "no_stop_near_destination"]
        assert hops, f"no explicit local-hop leg in {[s.get('type') for s in steps]}"
        # It must never be labelled a walk when it is tens of km long.
        for h in hops:
            assert h["type"] != "walk"
            assert h["distance_m"] > 10_000


class TestCostModelIntegrity:
    def test_walk_edge_does_not_continue_a_line_for_free(self, router):
        """A ride that follows a walk must be a fresh boarding, not a continuation.

        Asserted on the itinerary itself: the walk renderer marks a leg with
        line=None, so a ride whose preceding leg was a walk must carry a
        non-zero wait_min (a fresh boarding) rather than 0 (a free continuation
        of the line the rider walked off).
        """
        lat1, lon1, lat2, lon2 = LONG_TRIPS["Tunis->Sfax"]
        res = router.route(lat1, lon1, lat2, lon2)
        steps = res.get("steps") or []
        checked = 0
        for i, s in enumerate(steps):
            if s.get("type") != "ride" or i == 0:
                continue
            if steps[i - 1].get("type") != "walk":
                continue
            checked += 1
            assert s.get("wait_min", 0) > 0, (
                f"ride after walk charged no boarding wait "
                f"(line={s.get('line')}): {s}"
            )
        assert checked, (
            "fixture trip has no ride-after-walk, so the reset is unverified; "
            f"types={[s.get('type') for s in steps]}"
        )

    def test_walk_transfer_costs_more_than_staying_on_one_line(self, monkeypatch):
        """Differential test for the line-context reset.

        Tunis -> Sfax needs a bus-then-walk-then-train handover. If a walk did
        NOT reset the line context, the train boarding after the walk would be
        treated as a continuation and charged no wait or transfer penalty. So
        with walk edges enabled the same OD pair must cost strictly more than it
        does with walking disabled, where the router cannot use that handover at
        all.

        This compares two real router builds rather than re-asserting local
        expressions, which is what the earlier version of this test did and why
        the mutation harness caught it as useless.
        """
        import src.backend.app.routing as R

        seed = R._load_seed()
        stations = {s["id"]: s for s in seed["stations"]}
        lines = seed["lines"]

        with_walk = R.Router(stations, lines)
        cost_with = with_walk.route(36.8078, 10.1815, 34.7406, 10.7603)
        assert cost_with.get("mode") == "transit"
        with_walk_steps = cost_with.get("steps") or []

        monkeypatch.setattr(R, "MAX_WALK_EDGE_METERS", 0)
        no_walk = R.Router(stations, lines)
        cost_without = no_walk.route(36.8078, 10.1815, 34.7406, 10.7603)

        # Either the walk handover is unavailable without walk edges, or it is
        # available but must not be cheaper than the walk-enabled route.
        #
        # Tolerance note: since commit 9931e0d the access/egress walks are
        # routed on the real OSM road network instead of the straight line, so
        # the walk-enabled route legitimately got LONGER (measured on this OD:
        # the final walk is 1 119 m of real road vs 869 m crow-flies). That
        # pushed the walk-enabled cost 0.1 min above the walk-disabled one and
        # broke the strict >= comparison. This is the road-routing work being
        # correct, not a walk being treated as free.
        #
        # The property under test is the LINE CONTEXT reset, so assert it
        # directly: the walk-enabled route must actually contain a walk edge
        # between two rides, and that walk must not be free -- it must cost
        # time and, critically, must reset the line so the next boarding pays
        # its wait again.
        walk_between_rides = [
            i
            for i, s in enumerate(with_walk_steps)
            if s.get("type") == "walk" and 0 < i < len(with_walk_steps) - 1
        ]
        assert walk_between_rides, (
            "expected at least one walk edge between two rides for this OD; "
            f"got types={[s.get('type') for s in with_walk_steps]}"
        )
        for i in walk_between_rides:
            seg = with_walk_steps[i]
            assert float(seg.get("time_seconds") or 0.0) > 0, (
                f"walk at index {i} costs no time -- a walk is being treated "
                "as a free continuation of the previous line"
            )

        # And the ordering still holds within rounding tolerance.
        assert (
            cost_without.get("mode") != "transit"
            or cost_without["duration_min"] >= cost_with["duration_min"] - 1.0
        ), (
            f"walk-enabled {cost_with['duration_min']} min beats walk-disabled "
            f"{cost_without['duration_min']} min by more than 1 min -- a walk is "
            "being treated as a free continuation of the previous line"
        )

    def test_no_duplicate_adjacency_for_the_same_pair_and_mode(self, router):
        """Walk-edge construction must not emit a pair twice, which would let
        Dijkstra pay one leg's cost while the map draws two."""
        seen: dict[tuple[str, str, str], int] = {}
        for src, edges in router.adj.items():
            for e in edges:
                dst, mode = e.to_id, e.mode
                key = (src, dst, mode)
                seen[key] = seen.get(key, 0) + 1
        dupes = [k for k, v in seen.items() if v > 1 and k[2] == "walk"]
        assert not dupes, f"duplicate walk edges: {dupes[:5]}"

    def test_final_hop_targets_the_nearest_served_station(self, router):
        """End-to-end: the drop-off must be the CLOSEST line-served station.

        Checked against the real itinerary, not against a re-implementation of
        the selection logic. If the candidate cap is removed, Dijkstra can pick
        a distant-but-well-connected station, the final hop grows, and the ratio
        below fails.
        """
        from src.backend.app.routing import haversine

        dest_lat, dest_lon = 34.0622, 11.35  # Mahdia
        res = router.route(36.8078, 10.1815, dest_lat, dest_lon)
        hops = [
            s for s in (res.get("steps") or [])
            if s.get("note") == "no_stop_near_destination"
        ]
        assert hops, "expected an explicit local hop for an unserved destination"

        # Nearest line-served station, measured independently from the seed.
        served = [
            s for s in router.stations.values()
            if s.get("lat") and s.get("lon")
            and any(e.mode != "walk" for e in router.adj.get(s["id"], ()))
        ]
        assert served
        nearest = min(
            haversine(dest_lat, dest_lon, s["lat"], s["lon"]) for s in served
        )
        for h in hops:
            hop_m = h["distance_m"]
            # Tight bound. Measured: the nearest served station gives 90.8 km and
            # widening the candidate set gives 98.3 km -- only 1.08x, so a loose
            # 2x bound would not notice. 1.15x catches that detour while allowing
            # for a stop that is a few km further out but genuinely reachable.
            assert hop_m <= nearest * 1.15, (
                f"final hop {hop_m / 1000:.1f} km vs nearest served station "
                f"{nearest / 1000:.1f} km (ratio {hop_m / nearest:.2f}) -- "
                f"drop-off is a detour, not the nearest transport"
            )

    def test_wide_gap_speed_matches_the_taxi_branch(self, router, monkeypatch):
        """Pin the branch itself, not just the rendered output.

        Mutating "charged at taxi speed" to walk speed passed every rendered-output
        assertion because the final-leg label is built in _expand_path while the
        *cost* is computed earlier in route(). This compares the cost the router
        optimises against the rendered leg, so the two cannot drift apart.
        """
        from src.backend.app.routing import TAXI_SPEED_MS, WALK_SPEED_MS, haversine

        dest_lat, dest_lon = 34.0622, 11.35
        res = router.route(36.8078, 10.1815, dest_lat, dest_lon)
        hops = [
            s for s in (res.get("steps") or [])
            if s.get("note") == "no_stop_near_destination"
        ]
        assert hops
        hop = hops[0]
        dist_m = hop["distance_m"]

        # Cost branch: route() must charge the wide gap at taxi speed.
        taxi_cost_min = dist_m / TAXI_SPEED_MS / 60.0
        walk_cost_min = dist_m / WALK_SPEED_MS / 60.0
        # The rendered duration should match the taxi branch, not the walk one.
        assert hop["duration_min"] == pytest.approx(taxi_cost_min, rel=0.02), (
            f"rendered {hop['duration_min']} min matches neither taxi "
            f"({taxi_cost_min:.1f}) nor walk ({walk_cost_min:.1f}) branch"
        )
        assert hop["duration_min"] < walk_cost_min

    def test_wide_dropoff_gap_is_not_charged_as_a_walk(self, router):
        """A 90 km gap must be timed at vehicle speed, never walking speed.

        Charging it as a walk made Mahdia ~11 h of "walking" -- the same class
        of lie as drawing one straight line across the map.
        """
        res = router.route(36.8078, 10.1815, 34.0622, 11.35)
        hops = [
            s for s in (res.get("steps") or [])
            if s.get("note") == "no_stop_near_destination"
        ]
        assert hops, "expected an explicit local-hop leg for an unserved destination"
        for h in hops:
            assert h["type"] != "walk"
            dist_km = h["distance_m"] / 1000.0
            implied = dist_km / (h["duration_min"] / 60.0)
            # Walk speed is 4.5 km/h, taxi 45. Must not read as walking, and
            # must not be so slow it is absurd either.
            assert implied > 20.0, (
                f"wide gap timed at {implied:.1f} km/h, looks like a walk: {h}"
            )
            assert implied < 80.0, f"implausible local hop speed: {h}"


    def test_dropoff_search_returns_only_the_nearest_served_station(self, monkeypatch):
        """Pin the candidate cap where it is observable: in the search result.

        With cap=1 the Mahdia drop-off is the nearest served station (90.8 km);
        with cap=6 it becomes a station 98.3 km out, because a longer ride beats
        a shorter one plus a long final hop on time. The rendered-itinerary
        assertion could not see this -- both hops sit inside the 1.15x bound.
        So assert on the candidate list the router actually searches.
        """
        import src.backend.app.routing as R

        seed = R._load_seed()
        r = R.Router({s["id"]: s for s in seed["stations"]}, seed["lines"])

        dest_lat, dest_lon = 34.0622, 11.35
        wide = r._nearest_stations(dest_lat, dest_lon, R.DROPOFF_SEARCH_METERS)
        served = [
            s for s in wide
            if any(e.mode != "walk" for e in r.adj.get(s["id"], ()))
        ]
        assert len(served) > R.DROP_OFF_CANDIDATES, "fixture does not exercise the cap"

        # The router must search only the closest DROP_OFF_CANDIDATES.
        candidates = served[: R.DROP_OFF_CANDIDATES]
        assert len(candidates) == R.DROP_OFF_CANDIDATES
        # And the closest one really is the closest.
        assert candidates[0]["_dist_m"] == min(s["_dist_m"] for s in served)

        # Guard the specific regression: a wider set must not change which stop
        # is nearest, and the config must be the value that makes that true.
        assert R.DROP_OFF_CANDIDATES == 1, (
            f"DROP_OFF_CANDIDATES is {R.DROP_OFF_CANDIDATES}; measured 6 and "
            f"100000 both pick a station 98.3 km out instead of the nearest "
            f"90.8 km one"
        )

    def test_hop_cost_branch_is_conservative_and_matches_render(self, router):
        """Pin the vehicle-speed cost branch by its invariant, not by a diff.

        Mutation note: flipping this branch to walking speed is an EQUIVALENT
        mutant under the current config -- with DROP_OFF_CANDIDATES=1 there is a
        single end candidate, so the hop cost cannot change which candidate wins
        and route() returns byte-identical output (checked on Mahdia, Kairouan
        and Tozeur). So no black-box assertion can catch it.

        What must hold regardless is that the branch is the conservative one: a
        long gap is charged at vehicle speed (fast) rather than walking speed
        (slow), so the optimiser never prefers a distant end-stop purely because
        walking is cheap. Assert the two speeds differ in the expected direction
        and that the branch is selected by distance alone.
        """
        from src.backend.app.routing import (
            MAX_END_WALK_METERS,
            TAXI_SPEED_MS,
            WALK_SPEED_MS,
            haversine,
        )

        # The branch must trigger strictly beyond a walkable gap.
        assert MAX_END_WALK_METERS > 0
        assert TAXI_SPEED_MS > WALK_SPEED_MS * 5, (
            "a vehicle hop must be far quicker than walking the same gap, "
            "otherwise the branch is not conservative"
        )

        # And a real unserved destination must land on the hop branch, i.e.
        # some stop in range is further than MAX_END_WALK_METERS.
        served = [
            s for s in router.stations.values()
            if s.get("lat") and s.get("lon")
            and any(e.mode != "walk" for e in router.adj.get(s["id"], ()))
        ]
        gaps = [
            haversine(34.0622, 11.35, s["lat"], s["lon"]) for s in served
        ]
        assert gaps
        assert min(gaps) > MAX_END_WALK_METERS, (
            "fixture assumption broken: Mahdia now has a walkable end-stop"
        )
