"""Louage-taxi interchange: the two road-for-hire modes must connect.

Louage stations come from a separate seed with its own shape and were absent
from the routing graph entirely; taxi stations were present but had no edges
because no line calls at them. These tests pin the behaviour that fixed it:

  1. louage seed stations are merged into the router station dict
  2. transfer edges connect louage and taxi stations
  3. same-location pairs are zero-cost; nearby pairs are walk-cost, in radius
  4. transfer edges are bidirectional and never duplicate a walk edge
  5. the /route/plan endpoint surfaces a louage/taxi itinerary

Run:  python -m pytest tests/test_louage_taxi_transfers.py -q
"""
from __future__ import annotations

import pytest

from support import client, services

from bledi_transit.application.routing.graph import (
    LOUAGE_TAXI_EDGE,
    LOUAGE_TAXI_SAME_LOCATION_M,
    LOUAGE_TAXI_TRANSFER_RADIUS_M,
)
from bledi_transit.domain.geo import haversine_m
from bledi_transit.domain.modes import canonical_mode

# Tunis centre -> Bizerte, a corridor the louage network serves.
TUNIS_BIZERTE = (36.8078, 10.1815, 37.2744, 9.8739)


def _louage_and_taxi(router) -> tuple[list[str], list[str]]:
    louage: list[str] = []
    taxi: list[str] = []
    for sid, s in router.stations.items():
        if not (s.get("lat") and s.get("lon")):
            continue
        canon = canonical_mode(s.get("mode") or "")
        if canon == "louaj":
            louage.append(sid)
        elif canon == "taxi":
            taxi.append(sid)
    return louage, taxi


def _transfer_edges(router) -> list[tuple[str, object]]:
    return [
        (src, e)
        for src, edges in router.adj.items()
        for e in edges
        if e.line == LOUAGE_TAXI_EDGE
    ]


class TestLouageTaxiInterchange:
    def test_louage_seed_stations_are_merged(self, router):
        merged = [sid for sid in router.stations if sid.startswith("louage_")]
        assert len(merged) >= 10, f"only {len(merged)} louage seed stations merged"

    def test_both_mode_families_are_present(self, router):
        louage, taxi = _louage_and_taxi(router)
        assert louage, "no louage stations in the router"
        assert taxi, "no taxi stations in the router"

    def test_transfer_edges_exist_and_are_bidirectional(self, router):
        transfer = _transfer_edges(router)
        assert transfer, "no louage-taxi transfer edges"
        fwd = {(src, e.to_id) for src, e in transfer}
        bwd = {(e.to_id, src) for src, e in transfer}
        assert fwd == bwd, "louage-taxi transfer edges are not bidirectional"

    def test_same_location_pairs_are_zero_cost(self, router):
        zero = [(src, e) for src, e in _transfer_edges(router) if e.time_s == 0.0]
        assert zero, "no zero-cost same-location transfer edges"
        src, e = zero[0]
        a, b = router.stations[src], router.stations[e.to_id]
        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        assert d <= LOUAGE_TAXI_SAME_LOCATION_M, f"{a['name']} <-> {b['name']} is {d:.0f}m"

    def test_nearby_pairs_are_walk_cost_and_in_radius(self, router):
        nearby = [(src, e) for src, e in _transfer_edges(router) if e.time_s > 0.0]
        assert nearby, "no walk-cost nearby transfer edges"
        for _, e in nearby:
            assert 0 < e.straight_m <= LOUAGE_TAXI_TRANSFER_RADIUS_M + 1e-6

    def test_no_station_is_left_isolated(self, router):
        louage, taxi = _louage_and_taxi(router)
        isolated = [sid for sid in (louage + taxi) if not router.adj.get(sid)]
        assert not isolated, f"isolated louage/taxi stations: {isolated[:5]}"

    def test_transfer_edges_never_duplicate_a_walk_edge(self, router):
        """A pair already joined by a walk edge must not gain a second edge,
        which would let Dijkstra pay one cost while the map draws two."""
        seen: dict[tuple[str, str], int] = {}
        for src, edges in router.adj.items():
            for e in edges:
                if e.mode == "walk":
                    seen[(src, e.to_id)] = seen.get((src, e.to_id), 0) + 1
        dupes = [k for k, v in seen.items() if v > 1]
        assert not dupes, f"duplicate walk adjacency: {dupes[:5]}"


class TestPlanEndpointSurfacesRoadForHire:
    def test_louage_only_request_yields_a_louage_itinerary(self):
        resp = client().get(
            "/api/v1/route/plan",
            params={
                "start_lat": TUNIS_BIZERTE[0],
                "start_lon": TUNIS_BIZERTE[1],
                "end_lat": TUNIS_BIZERTE[2],
                "end_lon": TUNIS_BIZERTE[3],
                "modes_include": "louaj,taxi",
            },
        )
        assert resp.status_code == 200
        itineraries = resp.json().get("itineraries", [])
        assert itineraries, "no itineraries for a louaj/taxi request"
        modes = {m for it in itineraries for m in it.get("modes_used", [])}
        assert modes & {"louaj", "taxi"}, f"no road-for-hire mode in {sorted(modes)}"