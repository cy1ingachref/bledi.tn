"""The transit graph: one directed edge per consecutive stop pair, plus walk edges."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from bledi_transit.domain.geo import haversine_m, oriented_geometry, polyline_length
from bledi_transit.domain.tunables import GEOMETRY_REQUIRED_M, SPEED_BY_MODE, WALK_SPEED_MS

Segments = dict[str, dict[str, Any]]

# The line of a walk edge. After a walk the next boarding pays its wait again,
# and the sentinel never equals a real line id.
WALK_EDGE = "__walk__"


def transit_speed_kmh(mode: str) -> float:
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])


def transit_speed_ms(mode: str) -> float:
    return transit_speed_kmh(mode) / 3.6


@dataclass(slots=True)
class Edge:
    """One directed graph edge.

    distance_m follows the geometry when there is one, so the cost model and
    the drawn line agree. Empty `geometry` means no real path was found.
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
        # Shorter than the straight line means a mis-oriented or mis-stitched
        # slice in the cache.
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

    Without them a stop no line calls at is unreachable. A grid of
    walk-radius cells replaces the O(n^2) scan, which would add seconds to
    every start.
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
                    # Not live-routed: a live A* for each of the ~12 700 pairs
                    # would add minutes to startup. The itinerary resolves the
                    # real path only for the walks a rider sees.
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
