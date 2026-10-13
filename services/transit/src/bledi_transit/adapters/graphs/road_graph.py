"""Real-road paths on the Tunisia road graph, for walk and taxi legs.

The access walk, the final walk and a taxi leg have endpoints that are not
stations. A straight line between them crosses buildings and sometimes the
sea, so both endpoints are snapped onto the OSM road graph and the real road
polyline is returned instead.

data/road_graph.npz is built by tools/build_road_graph.py from the HotOSM
GeoPackage: ~6.3M nodes and 13M directed edges with a speed column per mode.
Travel time (length / speed) is the A* cost, so the route is the fastest one.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bledi_transit.adapters.graphs.search import Graph, astar, snap_candidates
from bledi_transit.domain.geo import haversine_m, polyline_length

# Column of each mode in the npz speed table. The build also writes a bike
# column, which no leg uses.
MODE_COL = {"car": 0, "foot": 1}

# A destination further than this from any road gets no road line rather than
# one that is obviously not a path.
MAX_SNAP_M = 250.0
# Measured on this graph: Tunis to Sousse (160 km of road) needs ~1.4M node
# expansions and Tunis to Gabes more. 900k reported "no route" for reachable
# places, so the cap comes from the measured worst case in
# verify_road_routing.py.
MAX_EXPAND_NODES = 12_000_000
SNAP_CANDIDATES = 6
# Extra A* runs the near-miss fallback may spend, so a bad snap degrades to the
# caller's fallback instead of stalling a request.
FALLBACK_ASTAR_TRIES = 4


def _default_graph_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(
        os.path.join(here, "..", "..", "..", "..", "..", "..", "data", "road_graph.npz")
    )


_CACHE: dict[str, Graph | None] = {}
# An itinerary asks for the same access walk and taxi road on every re-render
# of a trip, and a long A* costs seconds.
_ROUTE_MEMO: dict[tuple[str, str, str, int, str], "RoadRoute | None"] = {}
_ROUTE_MEMO_MAX = 512


def road_route_cached(
    g: Graph,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    mode: str = "car",
    *,
    max_snap_m: float = MAX_SNAP_M,
) -> RoadRoute | None:
    """Memoised road_route(). Coordinates quantised to 5dp (~1 m)."""
    key = (mode, f"{a_lat:.5f},{a_lon:.5f}", f"{b_lat:.5f},{b_lon:.5f}", int(max_snap_m), str(id(g)))
    if key in _ROUTE_MEMO:
        return _ROUTE_MEMO[key]
    r = road_route(g, a_lat, a_lon, b_lat, b_lon, mode, max_snap_m=max_snap_m)
    if len(_ROUTE_MEMO) >= _ROUTE_MEMO_MAX:
        _ROUTE_MEMO.clear()
    _ROUTE_MEMO[key] = r
    return r


def load_graph(path: str | None = None, *, log: Any = None) -> Graph | None:
    """Load and index the road graph. Returns None (and warns once) if absent."""
    path = os.path.abspath(path or os.environ.get("ROAD_GRAPH_PATH") or _default_graph_path())
    if path in _CACHE:
        return _CACHE[path]
    if not os.path.exists(path):
        if log:
            log.warning(
                "road routing: no graph at %s; road legs fall back to straight "
                "lines. Build it with: python services/transit/tools/build_road_graph.py",
                path,
            )
        _CACHE[path] = None
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
        # Optional: without labels a snap into another component just pays for
        # a failed search.
        for mode in MODE_COL:
            key = f"comp_{mode}"
            g.comp[mode] = z[key].astype(np.int32) if key in z.files else None

    order = np.argsort(g.eu, kind="stable")
    for mode, col in MODE_COL.items():
        # speed > 0 means usable, by build contract; the table stores m/s * 10.
        g.add_profile(mode, order, espec[:, col] > 0, (espec[:, col] / 10.0).astype(np.float32))

    _CACHE[path] = g
    if log:
        log.info(
            "road routing: graph %s loaded in %.1fs (%d nodes, %d edges; car %d, foot %d directed edges)",
            os.path.basename(path),
            time.time() - t0,
            g.n_nodes,
            g.n_edges,
            g.csr_edge["car"].size,
            g.csr_edge["foot"].size,
        )
    return g


def _snap(g: Graph, mode: str, lat: float, lon: float, max_m: float = MAX_SNAP_M) -> tuple[int, float] | None:
    got = snap_candidates(g, mode, lat, lon, max_m, want=1)
    return got[0] if got else None


def _simplify(pts: list[list[float]], tol_m: float = 8.0) -> list[list[float]]:
    """Drop vertices that bend the line by less than `tol_m` metres."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        total = haversine_m(a[0], a[1], c[0], c[1])
        if total < 1e-6:
            continue
        d = haversine_m(a[0], a[1], b[0], b[1]) + haversine_m(b[0], b[1], c[0], c[1])
        if d - total > tol_m:
            out.append(b)
    out.append(pts[-1])
    return out


@dataclass(slots=True)
class RoadRoute:
    geometry: list[list[float]]  # [[lat, lon], ...] along real roads
    distance_m: float
    duration_s: float
    snapped_from: tuple[float, float]
    snapped_to: tuple[float, float]
    snap_from_m: float
    snap_to_m: float
    road_names: list[str] = field(default_factory=list)


def road_route(
    g: Graph,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    mode: str = "car",
    *,
    max_snap_m: float = MAX_SNAP_M,
) -> RoadRoute | None:
    """Real-road route between two arbitrary points, or None if impossible.

    None means no road within `max_snap_m` of an endpoint, or the snapped nodes
    are not connected in this mode. The caller must never answer that with a
    straight line called a route.
    """
    if mode not in MODE_COL:
        mode = "car"
    # Nearest pair first, alternatives only when it fails: a full
    # SNAP_CANDIDATES^2 sweep multiplies a seconds-long search by up to 36.
    sa = _snap(g, mode, a_lat, a_lon, max_snap_m)
    sb = _snap(g, mode, b_lat, b_lon, max_snap_m)
    if sa is None or sb is None:
        return None
    src, dst = sa[0], sb[0]
    if src == dst:
        straight = haversine_m(a_lat, a_lon, b_lat, b_lon)
        return RoadRoute(
            geometry=[[a_lat, a_lon], [b_lat, b_lon]],
            distance_m=straight,
            duration_s=straight / max(float(g.speed_mps[mode].max()), 0.1),
            snapped_from=(float(g.lat[src]), float(g.lon[src])),
            snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
            snap_from_m=sa[1],
            snap_to_m=sb[1],
        )
    # Component labels come from the UNDIRECTED view of each mode, so different
    # labels prove there is no path and skip a 10 to 22 s search. Same labels
    # prove nothing: a one-way street can put a reachable pair in different
    # undirected components (56 351 of 12.6M car edges cross components), so
    # the labels only ever skip, never reject.
    labels = g.comp.get(mode)
    if labels is not None and int(labels[src]) != int(labels[dst]):
        found = None
    else:
        found = astar(g, mode, src, dst, MAX_EXPAND_NODES)
    if found is None:
        ca = snap_candidates(g, mode, a_lat, a_lon, max_snap_m, SNAP_CANDIDATES)
        cb = snap_candidates(g, mode, b_lat, b_lon, max_snap_m, SNAP_CANDIDATES)
        if labels is not None:
            # Same-component pairs first, the rest kept as fallbacks.
            target = int(labels[dst])
            cb.sort(key=lambda c: int(labels[c[0]]) != target)
            keep_comp = int(labels[cb[0][0]]) if cb else None
            if keep_comp is not None:
                ca.sort(key=lambda c: int(labels[c[0]]) != keep_comp)
        tried = 0
        for node_a, da in ca:
            for node_b, db in cb:
                if node_a == node_b or (node_a == src and node_b == dst):
                    continue
                tried += 1
                if tried > FALLBACK_ASTAR_TRIES:
                    ca = cb = []
                    break
                got = astar(g, mode, node_a, node_b, MAX_EXPAND_NODES)
                if got is not None:
                    found = got
                    sa = (node_a, da)
                    sb = (node_b, db)
                    src, dst = node_a, node_b
                    break
            if found is not None:
                break
        if found is None:
            return None
    edge_path, secs = found

    pts: list[list[float]] = [[a_lat, a_lon]]
    names: list[str] = []
    last_name: str | None = None
    for eid in edge_path:
        nm, fr, ar = g.names[int(g.ename[eid])]
        label = nm or fr or ar or ""
        if label and label != last_name:
            names.append(label)
        last_name = label or last_name
        nxt = int(g.ev[eid])
        pts.append([float(g.lat[nxt]), float(g.lon[nxt])])
    pts.append([b_lat, b_lon])

    return RoadRoute(
        geometry=_simplify(pts),
        distance_m=polyline_length(pts),
        duration_s=secs,
        snapped_from=(float(g.lat[src]), float(g.lon[src])),
        snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
        snap_from_m=sa[1],
        snap_to_m=sb[1],
        road_names=names,
    )
