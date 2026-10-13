"""Real-track geometry between any two points on the rail network.

data/route_geometry.json misses station pairs exactly on the rail lines
(train_23_sncft lacked 6 of 17), and each gap was drawn as a straight line.
Both endpoints are snapped onto the nearest OSM rail, light_rail or tram track
and joined by A* along it. Line ids only caption the result: two stations on
the same corridor get the track between them whether or not a seed line
claims they are connected. Points on different tracks get None, never a line
that does not exist.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bledi_transit.adapters.graphs.search import Graph, astar, snap_candidates
from bledi_transit.domain.geo import haversine_m, polyline_length

PROFILE = "all"
MAX_EXPAND_NODES = 4_000_000
# Generous on purpose: SNCFT station polygons and the seed's stop pins disagree
# by up to ~700 m in the south, and refusing to connect would bring the
# straight line back.
RAIL_SNAP_M = 900.0


_RAIL_CACHE: dict[str, Graph | None] = {}


def load_rail_graph(path: str, *, log: Any = None) -> Graph | None:
    path = os.path.abspath(path)
    if path in _RAIL_CACHE:
        return _RAIL_CACHE[path]
    if not os.path.exists(path):
        if log:
            log.warning(
                "rail geometry: no graph at %s; rail legs fall back to cached "
                "geometry or a straight line. Build it with: "
                "python services/transit/tools/build_rail_graph.py",
                path,
            )
        _RAIL_CACHE[path] = None
        return None

    t0 = time.time()
    with np.load(path, allow_pickle=True) as z:
        g = Graph(
            lat=z["lat"].astype(np.float64),
            lon=z["lon"].astype(np.float64),
            eu=z["eu"].astype(np.int32),
            ev=z["ev"].astype(np.int32),
            elen=z["elen"].astype(np.float64),
            ename=z["ename"].astype(np.int32),
            names=[tuple(x) for x in z["ename_raw"].tolist()],
        )
        espec = z["espec"].astype(np.float32)

    g.add_profile(
        PROFILE,
        np.argsort(g.eu, kind="stable"),
        espec[:, 0] > 0,
        (espec[:, 0] / 10.0).astype(np.float32),
    )
    _RAIL_CACHE[path] = g
    if log:
        log.info(
            "rail geometry: %s loaded in %.1fs (%d nodes, %d edges)",
            os.path.basename(path), time.time() - t0, g.n_nodes, g.n_edges,
        )
    return g


@dataclass(slots=True)
class RailTrack:
    geometry: list[list[float]]      # [[lat, lon], ...] along real track
    distance_m: float
    snapped_from: tuple[float, float]
    snapped_to: tuple[float, float]
    snap_from_m: float
    snap_to_m: float
    classes: list[str] = field(default_factory=list)


def track_between(
    g: Graph,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    max_snap_m: float = RAIL_SNAP_M,
) -> RailTrack | None:
    """The real track polyline between two points, or None if none connects."""
    sa = snap_candidates(g, PROFILE, a_lat, a_lon, max_snap_m, want=1)
    sb = snap_candidates(g, PROFILE, b_lat, b_lon, max_snap_m, want=1)
    if not sa or not sb:
        return None
    (src, snap_from_m), (dst, snap_to_m) = sa[0], sb[0]
    if src == dst:
        return RailTrack(
            geometry=[[a_lat, a_lon], [b_lat, b_lon]],
            distance_m=haversine_m(a_lat, a_lon, b_lat, b_lon),
            snapped_from=(float(g.lat[src]), float(g.lon[src])),
            snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
            snap_from_m=snap_from_m,
            snap_to_m=snap_to_m,
        )
    found = astar(g, PROFILE, src, dst, MAX_EXPAND_NODES)
    if found is None:
        return None
    edge_path, _secs = found

    pts: list[list[float]] = [[a_lat, a_lon]]
    classes: list[str] = []
    last: str | None = None
    for eid in edge_path:
        wid = int(g.ename[eid])
        label = g.names[wid][0] if wid < len(g.names) else ""
        if label and label != last:
            classes.append(label)
        last = label
        nxt = int(g.ev[eid])
        pts.append([float(g.lat[nxt]), float(g.lon[nxt])])
    pts.append([b_lat, b_lon])

    return RailTrack(
        geometry=pts,
        distance_m=polyline_length(pts),
        snapped_from=(float(g.lat[src]), float(g.lon[src])),
        snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
        snap_from_m=snap_from_m,
        snap_to_m=snap_to_m,
        classes=classes,
    )


_RAIL_MEMO: dict[tuple[str, str, str], RailTrack | None] = {}
_MISSING: Any = object()


def track_between_cached(
    g: Graph, a_lat: float, a_lon: float, b_lat: float, b_lon: float,
    max_snap_m: float = RAIL_SNAP_M,
) -> RailTrack | None:
    key = (f"{a_lat:.5f},{a_lon:.5f}", f"{b_lat:.5f},{b_lon:.5f}", str(id(g)))
    # One get, not `in` then `[]`: request threads may clear the memo in between.
    hit = _RAIL_MEMO.get(key, _MISSING)
    if hit is not _MISSING:
        return hit
    t = track_between(g, a_lat, a_lon, b_lat, b_lon, max_snap_m)
    if len(_RAIL_MEMO) >= 4096:
        _RAIL_MEMO.clear()
    _RAIL_MEMO[key] = t
    return t
