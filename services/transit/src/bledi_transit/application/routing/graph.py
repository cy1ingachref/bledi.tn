"""The transit graph: one directed edge per consecutive stop pair, plus walk edges."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from bledi_transit.domain.geo import haversine_m, oriented_geometry, polyline_length
from bledi_transit.domain.tunables import GEOMETRY_REQUIRED_M, SPEED_BY_MODE, WALK_SPEED_MS

Segments = dict[str, dict[str, Any]]

# A walk edge resets the line context: after walking you have not "arrived on"
# any line, so the next boarding is a fresh boarding (wait paid again) rather
# than a free continuation. The sentinel keeps that distinct from a real line id.
WALK_EDGE = "__walk__"


def transit_speed_kmh(mode: str) -> float:
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])


def transit_speed_ms(mode: str) -> float:
    return transit_speed_kmh(mode) / 3.6


@dataclass(slots=True)
class Edge:
    """One directed graph edge.

    distance_m is the REAL along-geometry distance, not the straight line, so
    the cost model and the drawn line agree. straight_m is kept only for the
    A* heuristic and for auditing how much the real path detours.

    `geometry` empty means "no real path was found". `needs_geometry` records
    whether that absence is visible enough to matter, so the API can refuse to
    draw a straight line instead of silently producing an off-road one.
    """
    to_id: str
    line: str
    mode: str
    wait_s: float
    distance_m: float
    time_s: float
    geometry: list[list[float]]
    straight_m: float

    @property
    def needs_geometry(self) -> bool:
        return not self.geometry and self.straight_m >= GEOMETRY_REQUIRED_M


def line_edge(
    segments: Segments,
    a_id: str,
    b_id: str,
    a: dict[str, Any],
    b: dict[str, Any],
    ln_id: str,
    mode: str,
    wait_s: float,
) -> Edge:
    """One directed ride edge with real distance, time and geometry."""
    straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    entry = segments.get(f"{min(a_id, b_id)}|{max(a_id, b_id)}")
    geom: list[list[float]] = []
    real_m = straight_m
    if entry and entry.get("geometry"):
        geom = oriented_geometry(entry, a_id, b_id)
        # A path along a network cannot be shorter than the straight line it
        # replaces. Anything under that means the stored polyline is wrong
        # (a mis-oriented or mis-stitched slice), so refuse it and keep the
        # honest straight line rather than a physically impossible distance.
        cand_m = polyline_length(geom)
        if cand_m >= 0.95 * straight_m:
            real_m = cand_m
        else:
            geom = []
    if real_m <= 0:
        real_m = straight_m
    return Edge(
        to_id=b_id,
        line=ln_id,
        mode=mode,
        wait_s=wait_s,
        distance_m=real_m,
        time_s=real_m / transit_speed_ms(mode),
        geometry=geom,
        straight_m=straight_m,
    )


def add_walk_edges(
    adj: dict[str, list[Edge]],
    stations: dict[str, dict[str, Any]],
    walk_segments: Segments,
    max_walk_edge_m: float,
) -> None:
    """Connect nearby stops with bidirectional walk edges.

    Without these the graph is transit-only, so a destination stop that no
    line calls at is unreachable and the router falls back to a single taxi
    line drawn straight across the map. This is what lets the router answer
    "walk to the nearest stop, ride, walk to the destination".

    Built through a lat/lon grid rather than an O(n^2) scan: 4221 stops
    squared is ~9M haversine calls at import time, which would add seconds to
    every server start. The grid keys on ~300 m cells so only the surrounding
    cells are examined per stop.
    """
    pos: dict[str, tuple[float, float]] = {
        sid: (s["lat"], s["lon"])
        for sid, s in stations.items()
        if s.get("lat") and s.get("lon")
    }
    cell_deg = max(max_walk_edge_m, 100) / 111_000.0
    grid: dict[tuple[int, int], list[str]] = defaultdict(list)
    for sid, (lat, lon) in pos.items():
        grid[(int(lat / cell_deg), int(lon / cell_deg))].append(sid)

    span = 1 if max_walk_edge_m <= cell_deg * 2 else 2
    for sid, (lat, lon) in pos.items():
        cx, cy = int(lat / cell_deg), int(lon / cell_deg)
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                for other in grid.get((cx + dx, cy + dy), ()):
                    # Both cells see both stops, so without this guard every
                    # pair is built twice; the extra appends are exact duplicates.
                    if other <= sid:
                        continue
                    o_lat, o_lon = pos[other]
                    d = haversine_m(lat, lon, o_lat, o_lon)
                    if d > max_walk_edge_m:
                        continue
                    # Geometry here is deliberately NOT live-routed. This loop
                    # builds every station pair within 900 m (12 736 of them in
                    # the current seed) and a live A* per pair would add minutes
                    # to process startup. The precomputed walk cache is used if
                    # present; the itinerary fills in the real pedestrian path
                    # lazily, per leg, only for a walk the user actually sees.
                    wentry = walk_segments.get(f"{min(sid, other)}|{max(sid, other)}")
                    wgeom: list[list[float]] = []
                    wlen = d
                    if wentry and wentry.get("geometry"):
                        cand = oriented_geometry(wentry, sid, other)
                        cand_m = polyline_length(cand)
                        if cand_m >= 0.95 * d:
                            wgeom = cand
                            wlen = cand_m
                    for src, dst in ((sid, other), (other, sid)):
                        adj[src].append(
                            Edge(
                                to_id=dst,
                                line=WALK_EDGE,
                                mode="walk",
                                wait_s=0.0,
                                distance_m=wlen,
                                time_s=wlen / WALK_SPEED_MS,
                                geometry=wgeom,
                                straight_m=d,
                            )
                        )
