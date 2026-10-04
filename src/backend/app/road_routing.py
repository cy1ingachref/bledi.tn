"""Real-road routing on a self-contained Tunisia road graph.

Why this exists
---------------
The itinerary router in app/routing.py walks the *transit* network: stations
connected by bus/rail lines. That is correct for the middle of a journey but
leaves three gaps, all of which are drawn as a straight line today:

  * the access walk from an arbitrary origin to its first stop,
  * the final walk from the last stop to the destination,
  * a taxi / louaj leg, whose endpoints are never stations.

A straight line between two real points is not a path anyone can walk or
drive: it crosses buildings, walls and sometimes the sea. This module snaps
both endpoints onto the OSM road graph and returns the actual polyline, so
every leg in the app is a road that exists in the data.

Graph
-----
data/road_graph.npz holds one node table and one directed-edge table with a
per-mode speed column, built by tool/build_road_graph.py from the HotOSM
Tunisia GeoPackage. At import we build a CSR (node -> outgoing edge ids) per
mode; the whole road network is ~6.3M nodes / 13M edges, which is why this
uses flat numpy arrays and a heap rather than node objects.

Modes
-----
car / foot / bike. Speeds are per OSM highway class and are used two ways:
travel time = length / speed, and that same travel time is the A* cost, so
the default route is the fastest one for that mode.
"""

from __future__ import annotations

import heapq
import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

MODE_CAR, MODE_FOOT, MODE_BIKE = 1, 2, 4
MODE_BIT = {"car": MODE_CAR, "foot": MODE_FOOT, "bike": MODE_BIKE}
MODE_COL = {"car": 0, "foot": 1, "bike": 2}

EARTH_R = 6371008.8

# Defaults for a destination that is further than this from any road: refuse to
# invent a line rather than draw one that is obviously not a path.
MAX_SNAP_M = 250.0
# Search radius cap so a far-away destination cannot trigger a whole-country
# search inside a request.
# Search budget. Measured on this graph: Tunis->Sousse (160 km of real road)
# needs ~1.4M node expansions; Tunis->Gabes needs more. 900k truncated the
# search mid-flight and reported "no route" for perfectly reachable places, so
# the cap is set from the measured worst case in verify_road_routing.py rather
# than guessed low.
MAX_EXPAND_NODES = 12_000_000
# How many nearest road nodes to try per endpoint. More than one because the
# nearest node can sit on an unconnected stub; see _snap_candidates.
SNAP_CANDIDATES = 6
# How many extra A* runs the near-miss fallback may cost. Kept small so a bad
# snap degrades to the caller's fallback quickly instead of stalling a request.
FALLBACK_ASTAR_TRIES = 4
# How far past the straight-line travel time a search may go before it is
# declared unreachable. See the cost_cap in _astar.
UNREACHABLE_COST_FACTOR = 25.0
# Snap-index cell size in degrees (~2.2 km N-S at Tunisia's latitude).
GRID_CELL_DEG = 0.02


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def _default_graph_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(
        os.path.join(here, "..", "..", "..", "data", "road_graph.npz")
    )


@dataclass(slots=True)
class RoadGraph:
    lat: np.ndarray
    lon: np.ndarray
    eu: np.ndarray
    ev: np.ndarray
    elen: np.ndarray
    espec: np.ndarray  # (n_edges, 3) metres/sec * 10
    ename: np.ndarray
    names: list[tuple[str, str, str]]
    # per-mode CSR
    csr_off: dict[str, np.ndarray]
    csr_edge: dict[str, np.ndarray]
    speed_mps: dict[str, np.ndarray]
    grid: dict[str, dict[str, Any]]  # mode -> uniform grid index for snapping
    comp: dict[str, np.ndarray | None]  # mode -> component id per node
    # equirectangular projection helpers, set per query in _snap
    _coslat: float = 1.0

    @property
    def n_nodes(self) -> int:
        return int(self.lat.shape[0])

    @property
    def n_edges(self) -> int:
        return int(self.eu.shape[0])


_CACHE: dict[str, RoadGraph | None] = {}
# Per-process memo for repeated queries. An itinerary asks for the same
# access walk and the same taxi road on every re-render of the same trip, and
# a long A* costs seconds, so this turns a repeated question into a dict hit.
_ROUTE_MEMO: dict[tuple[str, str, int, int, str], "RoadRoute | None"] = {}
_ROUTE_MEMO_MAX = 512


def road_route_cached(
    g: RoadGraph,
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


def load_graph(path: str | None = None, *, log: Any = None) -> RoadGraph | None:
    """Load and index the road graph. Returns None (and warns once) if absent."""
    path = os.path.abspath(path or os.environ.get("ROAD_GRAPH_PATH") or _default_graph_path())
    if path in _CACHE:
        return _CACHE[path]
    if not os.path.exists(path):
        if log:
            log.warning(
                "road routing: no graph at %s; road legs fall back to straight "
                "lines. Build it with: python src/backend/tool/build_road_graph.py",
                path,
            )
        _CACHE[path] = None
        return None

    import time

    t0 = time.time()
    with np.load(path, allow_pickle=True) as z:
        lat = z["lat"].astype(np.float64)
        lon = z["lon"].astype(np.float64)
        eu = z["eu"].astype(np.int32)
        ev = z["ev"].astype(np.int32)
        elen = z["elen"].astype(np.float64)
        espec = z["espec"].astype(np.float32)
        ename = z["ename"].astype(np.int32)
        names = [tuple(x) for x in z["ename_raw"].tolist()]
        # Component labels are optional: a graph built before this was added
        # still works, it just pays for a failed search when a snap lands in a
        # different component.
        comp = {}
        for mode in MODE_BIT:
            key = f"comp_{mode}"
            comp[mode] = z[key].astype(np.int32) if key in z.files else None

    n = int(lat.shape[0])
    flags_by_mode: dict[str, np.ndarray] = {}
    for mode, bit in MODE_BIT.items():
        col = MODE_COL[mode]
        flags_by_mode[mode] = espec[:, col] > 0  # speed>0 == usable, by build contract

    csr_off: dict[str, np.ndarray] = {}
    csr_edge: dict[str, np.ndarray] = {}
    speed_mps: dict[str, np.ndarray] = {}
    grid: dict[str, dict[str, Any]] = {}
    for mode in MODE_BIT:
        usable = flags_by_mode[mode]
        # Sort edges by source node once, then take the usable slice per mode.
        order = np.argsort(eu, kind="stable")
        src_sorted = eu[order]
        deg = np.bincount(src_sorted, minlength=n).astype(np.int64)
        off = np.zeros(n + 1, dtype=np.int64)
        np.cumsum(deg, out=off[1:])
        keep = usable[order]
        kept = order[keep]
        # compact the CSR: rebuild offsets from the kept edges
        keep_deg = np.bincount(eu[kept], minlength=n).astype(np.int64)
        off2 = np.zeros(n + 1, dtype=np.int64)
        np.cumsum(keep_deg, out=off2[1:])
        csr_off[mode] = off2
        csr_edge[mode] = kept.astype(np.int32)
        speed_mps[mode] = (espec[:, MODE_COL[mode]] / 10.0).astype(np.float32)
        # Snap index: only nodes that can actually start a move in this mode.
        has_out = keep_deg > 0
        grid[mode] = _build_grid(np.nonzero(has_out)[0], lat, lon, GRID_CELL_DEG)

    g = RoadGraph(
        lat=lat,
        lon=lon,
        eu=eu,
        ev=ev,
        elen=elen,
        espec=espec,
        ename=ename,
        names=names,
        csr_off=csr_off,
        csr_edge=csr_edge,
        speed_mps=speed_mps,
        grid=grid,
        comp=comp,
    )
    _CACHE[path] = g
    if log:
        log.info(
            "road routing: graph %s loaded in %.1fs (%d nodes, %d edges; car %d, "
            "foot %d, bike %d directed edges)",
            os.path.basename(path),
            time.time() - t0,
            g.n_nodes,
            g.n_edges,
            csr_edge["car"].size,
            csr_edge["foot"].size,
            csr_edge["bike"].size,
        )
    return g


def _build_grid(
    src_nodes: np.ndarray, lat: np.ndarray, lon: np.ndarray, cell: float
) -> dict[str, Any]:
    """Uniform grid over the nodes that have >=1 usable outgoing edge.

    Counting sort by cell id: `nodes` is ordered by cell, so cell c owns the
    slice nodes[off[c]:off[c + 1]]. Three numpy passes, no Python loop, and
    no per-node objects -- which matters at 6.3M nodes.
    """
    lat0 = float(lat.min())
    lon0 = float(lon.min())
    n_lat = int(np.floor((float(lat.max()) - lat0) / cell)) + 1
    n_lon = int(np.floor((float(lon.max()) - lon0) / cell)) + 1
    i = np.clip(((lat[src_nodes] - lat0) / cell).astype(np.int64), 0, n_lat - 1)
    j = np.clip(((lon[src_nodes] - lon0) / cell).astype(np.int64), 0, n_lon - 1)
    flat = i * n_lon + j
    order = np.argsort(flat, kind="stable")
    sorted_flat = flat[order]
    n_cells = n_lat * n_lon
    counts = np.bincount(sorted_flat, minlength=n_cells)
    off = np.zeros(n_cells + 1, dtype=np.int64)
    np.cumsum(counts, out=off[1:])
    return {
        "cell": cell,
        "lat0": lat0,
        "lon0": lon0,
        "n_lat": n_lat,
        "n_lon": n_lon,
        "off": off,
        "nodes": src_nodes[order].astype(np.int32),
    }


def _snap_candidates(
    g: RoadGraph,
    mode: str,
    lat: float,
    lon: float,
    max_m: float = MAX_SNAP_M,
    want: int = SNAP_CANDIDATES,
) -> list[tuple[int, float]]:
    """The `want` nearest usable road nodes, ascending by distance.

    A single nearest node is not enough. Measured case (verify_road_routing.py
    scenario): a station 125 m from the destination snapped in foot mode onto a
    degree-1 dead-end stub of an unnamed way, so A* found the two nodes
    disconnected and the leg fell back to a straight line -- while the *second*
    nearest foot node, 30 m further away, was on a through street and routed
    fine. Ranking only by distance therefore silently loses real paths.

    Returns up to `want` nodes within max_m, nearest first.
    """
    idx = g.grid[mode]
    if idx is None:
        return []

    cell = idx["cell"]
    lat0 = idx["lat0"]
    lon0 = idx["lon0"]
    n_lat = idx["n_lat"]
    n_lon = idx["n_lon"]

    ci = min(max(int((lat - lat0) / cell), 0), n_lat - 1)
    cj = min(max(int((lon - lon0) / cell), 0), n_lon - 1)
    max_ring = int(max_m / 111_320.0 / cell) + 1

    seen: dict[int, float] = {}
    for ring in range(0, max_ring + 1):
        # Stop once the best hit is provably closer than anything still
        # unexamined: a node in a cell at ring distance >= ring+1 lies at least
        # ring*cell away.
        if seen:
            best_d = min(seen.values())
            if ring * cell * 111_320.0 > best_d:
                break
        parts: list[np.ndarray] = []
        for di in range(-ring, ring + 1):
            for dj in range(-ring, ring + 1):
                if ring > 0 and max(abs(di), abs(dj)) != ring:
                    continue
                i, j = ci + di, cj + dj
                if not (0 <= i < n_lat and 0 <= j < n_lon):
                    continue
                flat = i * n_lon + j
                a, b = idx["off"][flat], idx["off"][flat + 1]
                if b > a:
                    parts.append(idx["nodes"][a:b])
        if not parts:
            continue
        cand = np.unique(np.concatenate(parts)) if len(parts) > 1 else parts[0]
        dist = _dist_to(g, cand, lat, lon)
        for node, d in zip(cand.tolist(), dist.tolist()):
            h = haversine_m(lat, lon, float(g.lat[node]), float(g.lon[node]))
            if h <= max_m and (node not in seen or h < seen[node]):
                seen[node] = h
    return sorted(((n, d) for n, d in seen.items()), key=lambda nd: nd[1])[:want]


def _snap(
    g: RoadGraph,
    mode: str,
    lat: float,
    lon: float,
    max_m: float = MAX_SNAP_M,
) -> tuple[int, float] | None:
    """Nearest road node usable by `mode`, with its distance in metres."""
    got = _snap_candidates(g, mode, lat, lon, max_m, want=1)
    return got[0] if got else None


def _dist_to(g: RoadGraph, nodes: np.ndarray, lat: float, lon: float) -> np.ndarray:
    """Equirectangular distance in metres from (lat,lon) to each node."""
    coslat = math.cos(math.radians(lat))
    dy = (g.lat[nodes] - lat) * 111_320.0
    dx = (g.lon[nodes] - lon) * 111_320.0 * coslat
    return np.hypot(dx, dy)


def _astar(
    g: RoadGraph,
    mode: str,
    src: int,
    dst: int,
    max_expand: int = MAX_EXPAND_NODES,
) -> tuple[list[int], float] | None:
    """A* on travel time. Returns (node path, seconds) or None."""
    n = g.n_nodes
    edge_ids = g.csr_edge[mode]
    off = g.csr_off[mode]
    eu = g.eu
    ev = g.ev
    elen = g.elen
    spd = g.speed_mps[mode]

    lat0, lon0 = float(g.lat[src]), float(g.lon[src])
    dlat0 = (g.lat - lat0) * 111_320.0
    dlon0 = (g.lon - lon0) * 111_320.0 * math.cos(math.radians(lat0))

    # Admissible heuristic: straight-line distance / the fastest speed this
    # mode has anywhere on the network. Cannot overestimate, so A* stays
    # optimal. Floor at 1 m/s to keep it finite where a speed is 0.
    max_spd = float(spd[edge_ids].max()) if edge_ids.size else 1.0
    max_spd = max(max_spd, 0.1)

    # Bound the search by what a real path could plausibly cost. A route between
    # two points d metres apart cannot legitimately take much longer than
    # d / slowest_speed, and in practice well under it. Without this an
    # unreachable pair exhausts the entire component (measured 10.7 s each, and
    # four of them made a single Tunis->Carthage request take 43 s).
    # The bound is a multiple of the straight-line time so a legitimate detour
    # -- around a mountain, a river, a one-way pair -- is never cut off.
    crow = math.hypot(float(dlat0[dst]), float(dlon0[dst]))
    min_speed = float(spd[edge_ids].min()) if edge_ids.size else 0.1
    min_speed = max(min_speed, 0.1)
    cost_cap = (crow / min_speed) * UNREACHABLE_COST_FACTOR

    g_score = np.full(n, np.inf, dtype=np.float64)
    # came[] holds the EDGE id used to reach a node, not the parent node, so the
    # path can be rebuilt with the real edge and its road name. Storing the
    # parent node instead loses the edge and, since the arrays are different
    # lengths, indexes off the end of the node array entirely.
    came_edge = np.full(n, -1, dtype=np.int64)
    g_score[src] = 0.0
    closed = np.zeros(n, dtype=bool)
    heap: list[tuple[float, int]] = [(0.0, src)]
    expanded = 0

    while heap:
        f, node = heapq.heappop(heap)
        if closed[node]:
            continue
        closed[node] = True
        if node == dst:
            edges: list[int] = []
            cur = dst
            while came_edge[cur] != -1:
                e = int(came_edge[cur])
                edges.append(e)
                cur = int(eu[e])
            edges.reverse()
            return edges, float(g_score[dst])
        expanded += 1
        if expanded > max_expand or f > cost_cap:
            return None
        gcur = g_score[node]
        for e in range(off[node], off[node + 1]):
            eid = int(edge_ids[e])
            nxt = int(ev[eid])
            if closed[nxt]:
                continue
            s = float(spd[eid])
            if s <= 0:
                continue
            cost = gcur + float(elen[eid]) / s
            if cost < g_score[nxt]:
                g_score[nxt] = cost
                came_edge[nxt] = eid
                h = math.hypot(float(dlat0[nxt]), float(dlon0[nxt])) / max_spd
                heapq.heappush(heap, (cost + h, nxt))
    return None


def _simplify(pts: list[list[float]], tol_m: float = 8.0) -> list[list[float]]:
    """Drop points that add no shape, keeping the line inside `tol_m` of the
    real road. A road vertex that lies within tolerance of the segment between
    its neighbours is redundant for drawing and for length."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        # perpendicular distance of b from segment a->c, in metres
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
    g: RoadGraph,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    mode: str = "car",
    *,
    max_snap_m: float = MAX_SNAP_M,
) -> RoadRoute | None:
    """Real-road route between two arbitrary points, or None if impossible.

    None means: no road within `max_snap_m` of one of the endpoints, or the two
    snapped nodes are not connected in this mode. The caller must treat that as
    "no road geometry available", never as a licence to draw a straight line
    and call it a route.
    """
    if mode not in MODE_BIT:
        mode = "car"
    # Snap the nearest node first and try that pair alone. Only when it yields
    # no path do we spend more searches on the alternatives: a full
    # SNAP_CANDIDATES^2 sweep multiplies the cost of a long route (seconds) by
    # up to 36, which is not affordable per request. Nearest-first keeps the
    # common case at exactly one A*, and the fallback exists for the case that
    # motivated it -- the nearest node sitting on an unconnected stub.
    sa = _snap(g, mode, a_lat, a_lon, max_snap_m)
    sb = _snap(g, mode, b_lat, b_lon, max_snap_m)
    if sa is None or sb is None:
        return None
    src, dst = sa[0], sb[0]
    # Cheap rejection first. Component labels are computed on the UNDIRECTED
    # view of each mode, so different labels prove there is no path and let us
    # skip a search that would otherwise burn 10-22 s proving the same thing.
    #
    # Same labels prove nothing and must never reject: a one-way street has a
    # forward edge but no reverse twin, so a legitimately reachable pair can sit
    # in different undirected components (measured: 56 351 of 12.6M car edges
    # are cross-component). The label check is a necessary condition for
    # reachability, not a sufficient one, so it is only ever used to skip.
    labels = g.comp.get(mode)
    if labels is not None and int(labels[src]) != int(labels[dst]):
        found = None
    elif src != dst:
        found = _astar(g, mode, src, dst)
    else:
        found = None
    if src == dst:
        # Both endpoints snapped onto the same node: there is no road to
        # search, just a short connector. Return the honest two-point geometry
        # immediately rather than starting a pointless search.
        return RoadRoute(
            geometry=[[a_lat, a_lon], [b_lat, b_lon]],
            distance_m=haversine_m(a_lat, a_lon, b_lat, b_lon),
            duration_s=haversine_m(a_lat, a_lon, b_lat, b_lon)
            / max(float(g.speed_mps[mode].max()), 0.1),
            snapped_from=(float(g.lat[src]), float(g.lon[src])),
            snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
            snap_from_m=sa[1],
            snap_to_m=sb[1],
        )
    if found is None:
        # Nearest pair is unreachable: widen the search to nearby road nodes.
        ca = _snap_candidates(g, mode, a_lat, a_lon, max_snap_m)
        cb = _snap_candidates(g, mode, b_lat, b_lon, max_snap_m)
        if labels is not None:
            # Prefer pairs that share a component (cheap to confirm) but keep
            # the mismatched ones as fallbacks, since a one-way pair can be
            # reachable across components.
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
                # Hard cap: an unreachable nearest pair already burned a full
                # A*. Without this the fallback could spend tens of seconds of a
                # single request chasing progressively less likely pairs.
                tried += 1
                if tried > FALLBACK_ASTAR_TRIES:
                    ca = cb = []
                    break
                got = _astar(g, mode, node_a, node_b)
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

    # Walk the real edges. Each edge's own OSM way contributes its name, so the
    # caller can say which road the traveller is actually on.
    pts: list[list[float]] = [[a_lat, a_lon]]
    names: list[str] = []
    last_name: str | None = None
    for eid in edge_path:
        wid = int(g.ename[eid])
        nm, fr, ar = g.names[wid]
        label = nm or fr or ar or ""
        if label and label != last_name:
            names.append(label)
        last_name = label or last_name
        nxt = int(g.ev[eid])
        pts.append([float(g.lat[nxt]), float(g.lon[nxt])])
    pts.append([b_lat, b_lon])

    length = 0.0
    for i in range(len(pts) - 1):
        length += haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

    return RoadRoute(
        geometry=_simplify(pts),
        distance_m=length,
        duration_s=secs,
        snapped_from=(float(g.lat[src]), float(g.lon[src])),
        snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
        snap_from_m=sa[1],
        snap_to_m=sb[1],
        road_names=names,
    )