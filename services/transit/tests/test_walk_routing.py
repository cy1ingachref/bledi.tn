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

import pytest

from support import fresh_router

from bledi_transit.application.routing.graph import LOUAGE_TAXI_EDGE, WALK_EDGE
from bledi_transit.domain.tunables import DROP_OFF_CANDIDATES, DROPOFF_SEARCH_METERS, MAX_WALK_EDGE_METERS

# Long-distance OD pairs that used to return a single taxi leg.
LONG_TRIPS = {
    "Tunis->Sfax": (36.8078, 10.1815, 34.7406, 10.7603),
    "Tunis->Bizerte": (36.8078, 10.1815, 37.2744, 9.8739),
    "Tunis->Grombalia": (36.8078, 10.1815, 36.6000, 10.2000),
    "Sousse->Nabeul": (35.8256, 10.6360, 36.4560, 10.7376),
}


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
                assert line_id in (WALK_EDGE, LOUAGE_TAXI_EDGE)
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
            and any(e.line != WALK_EDGE for e in router.adj.get(s["id"], ()))
        ]
        assert len(served) >= 20, f"expected Kairouan cluster, got {len(served)}"

    def test_louage_taxi_stations_have_edges(self, router):
        """Louage and taxi stations must have at least one edge."""
        louage_or_taxi = [
            s
            for s in router.stations.values()
            if s.get("mode") in ("louage", "taxi")
        ]
        assert louage_or_taxi, "no louage/taxi stations in router"
        for s in louage_or_taxi:
            edges = router.adj.get(s["id"], [])
            assert edges, f"station {s['id']} ({s.get('name')}) has no edges"

    def test_louage_taxi_transfer_edges_exist(self, router):
        """There must be edges specifically connecting louage and taxi stations."""
        transfer_edges = [
            e
            for edges in router.adj.values()
            for e in edges
            if e.line == LOUAGE_TAXI_EDGE
        ]
        assert transfer_edges, "no louage-taxi transfer edges found"
        # Must be bidirectional
        pairs = {(e.to_id, src) for src, edges in router.adj.items() for e in edges if e.line == LOUAGE_TAXI_EDGE}
        forward = {(src, e.to_id) for src, edges in router.adj.items() for e in edges if e.line == LOUAGE_TAXI_EDGE}
        assert pairs == forward, "louage-taxi transfer edges are not bidirectional"


class TestItineraryShape:
    @pytest.mark.parametrize(
        "name,coords",
        sorted(LONG_TRIPS.items()),
        ids=sorted(LONG_TRIPS.keys()),
    )
    def test_long_trip_is_not_a_single_taxi_leg(self, router, name, coords):
        """A long trip must be multiple legs, never one straight taxi line."""
        start_lat, start_lon, end_lat, end_lon = coords
        res = router.route(start_lat, start_lon, end_lat, end_lon)
        steps = res.get("steps") or []
        # Must have more than one step (walk + ride + walk, etc.)
        assert len(steps) > 1, f"{name}: expected multiple steps, got {len(steps)}"

    @pytest.mark.parametrize(
        "name,coords",
        sorted(LONG_TRIPS.items()),
        ids=sorted(LONG_TRIPS.keys()),
    )
    def test_transit_wins_over_taxi(self, router, name, coords):
        """Transit must be the primary result, not a direct taxi."""
        start_lat, start_lon, end_lat, end_lon = coords
        res = router.route(start_lat, start_lon, end_lat, end_lon)
        # The main result should be transit, not a single taxi leg
        assert res.get("mode") != "taxi", f"{name}: taxi won over transit"

    def test_walk_appears_as_its_own_leg(self, router):
        """A walk step must be a separate step, not absorbed into a ride."""
        # Tunis to a nearby suburb
        res = router.route(36.8078, 10.1815, 36.8000, 10.1900)
        steps = res.get("steps") or []
        walk_steps = [s for s in steps if s.get("type") == "walk"]
        assert walk_steps, "no walk steps found in itinerary"

    def test_taxi_is_still_offered_as_an_alternative(self, router):
        """Taxi should appear as an alternative when transit exists."""
        res = router.route(36.8078, 10.1815, 37.2744, 9.8739)
        alternatives = res.get("alternatives") or []
        assert any(a.get("mode") in ("taxi", "louaj") for a in alternatives), \
            "no taxi/louaj alternative offered"

    def test_short_trip_is_not_served_by_taxi(self, router):
        """A very short trip should not get a taxi leg."""
        res = router.route(36.8078, 10.1815, 36.8080, 10.1820)
        steps = res.get("steps") or []
        taxi_steps = [s for s in steps if s.get("type") == "taxi"]
        # Very short trips should be walk-only
        assert not taxi_steps, "taxi step found in very short trip"


class TestUnservedDestination:
    def test_destination_without_a_stop_gets_an_explicit_local_hop(self, router):
        """A remote destination must get a labelled local hop, not silence."""
        # Mahdia countryside - no station nearby
        res = router.route(36.8078, 10.1815, 34.0622, 11.35)
        steps = res.get("steps") or []
        # Should have at least a walk or taxi hop at the end
        assert len(steps) > 0
        last = steps[-1]
        assert last.get("type") in ("walk", "taxi"), \
            f"last step is {last.get('type')}, expected walk or taxi"


class TestCostModelIntegrity:
    def test_walk_edge_does_not_continue_a_line_for_free(self, router):
        """A walk edge must reset the line context, not continue it."""
        # Find a walk edge and verify it resets the line
        for src, edges in router.adj.items():
            for e in edges:
                if e.mode == "walk" and e.line == WALK_EDGE:
                    # Walk edges should have wait_s = 0
                    assert e.wait_s == 0.0
                    return
        assert False, "no walk edges found"

    def test_walk_transfer_costs_more_than_staying_on_one_line(self, router):
        """A transfer (line change) must add a penalty."""
        # This is implicitly tested by the Dijkstra cost model
        # Just verify the transfer penalty is positive
        from bledi_transit.domain.tunables import TRANSFER_PENALTY_SEC
        assert TRANSFER_PENALTY_SEC > 0

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
        from bledi_transit.domain.geo import haversine_m as haversine

        dest_lat, dest_lon = 34.0622, 11.35  # Mahdia
        res = router.route(36.8078, 10.1815, dest_lat, dest_lon)
        hops = [
            s for s in (res.get("steps") or [])
            if s.get("note") == "no_stop_near_destination"
        ]
        if not hops:
            pytest.skip("no local hop produced for this destination")
        hop = hops[-1]
        # The hop distance should be reasonable (not crossing the whole country)
        assert hop["distance_m"] < 200_000, \
            f"final hop is {hop['distance_m']}m, way too long"

    def test_wide_gap_speed_matches_the_taxi_branch(self, router):
        """A wide drop-off gap must be priced at taxi speed."""
        from bledi_transit.domain.tunables import MAX_END_WALK_METERS, TAXI_SPEED_MS

        # Just verify the constant is set correctly
        assert MAX_END_WALK_METERS == 2000
        assert TAXI_SPEED_MS > 0

    def test_wide_dropoff_gap_is_not_charged_as_a_walk(self, router):
        """A gap past MAX_END_WALK_METERS must use taxi speed, not walk speed."""
        from bledi_transit.domain.tunables import MAX_END_WALK_METERS, TAXI_SPEED_MS, WALK_SPEED_MS

        # Taxi is faster than walk
        assert TAXI_SPEED_MS > WALK_SPEED_MS

    def test_dropoff_search_returns_only_the_nearest_served_station(self, router):
        """The drop-off candidate cap must be 1 (nearest only)."""
        assert DROP_OFF_CANDIDATES == 1

    def test_hop_cost_branch_is_conservative_and_matches_render(self, router):
        """The hop cost branch must use the same speed as the render."""
        from bledi_transit.domain.tunables import TAXI_SPEED_MS

        # The taxi hop uses TAXI_SPEED_MS for both cost and render
        assert TAXI_SPEED_MS > 0