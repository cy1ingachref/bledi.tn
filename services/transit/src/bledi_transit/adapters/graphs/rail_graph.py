"""Real-track geometry between any two points on the rail network.

Companion to road_routing.py. Same idea, different network:

  road_routing  -> OSM highways, for walk / taxi / louaj legs
  THIS module   -> OSM rail + light_rail + tram, for train / metro / tram legs

The problem it solves
---------------------
`data/route_geometry.json` holds 1 776 station-pair polylines, but the rail
lines are exactly where the gaps are: train_23_sncft was missing 6 of 17 stop
pairs. Every one of those pairs was rendered as a STRAIGHT LINE between two
stops, which is what made the map look like it teleported to the next town and
came back.

The fix is the same trick used for roads, and it has nothing to do with line
numbers: snap both endpoints onto the nearest real TRACK, then A* along the
track. Line ids and numbers are only labels used to caption the result. Two
stations 20 km apart on the same corridor get the polyline that runs between
them whether or not any seed line claims they are connected.

If the two snapped points are on genuinely different tracks (a branch, a
disconnected freight line), this returns None and the caller says so rather than
drawing a line that does not exist.
"""

from __future__ import annotations

import heapq
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .road_routing import GRID_CELL_DEG, _build_grid, _dist_to, haversine_m

MODE_RAIL, MODE_LIGHT, MODE_TRAM = 1, 2, 4

# Search budget. A rail hop is at most a few hundred km of network; measured
# needs stay well inside this.
MAX_EXPAND_NODES = 4_000_000
# A rail station should be within this of a real track. Generous on purpose:
# SNCFT station polygons and the seed's stop pins disagree by up to ~700 m in
# the south, and refusing to connect would just bring the straight line back.
RAIL_SNAP_M = 900.0
# Same reasoning as road_routing.UNREACHABLE_COST_FACTOR: cap the search so an
# unreachable pair fails in seconds instead of exhausting its component.
UNREACHABLE_COST_FACTOR = 25.0


def _default_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(
        os.path.join(here, "..", "..", "..", "data", "rail_graph.npz")
    )


@dataclass(slots=True)
class RailGraph:
    lat: np.ndarray
    lon: np.ndarray
    eu: np.ndarray
    ev: np.ndarray
    elen: np.ndarray
    espec: np.ndarray  # (n_edges, 2) m/s * 10
    ename: np.ndarray
    names: list[tuple[str, str]]
    csr_off: dict[str, np.ndarray]
    csr_edge: dict[str, np.ndarray]
    speed_mps: dict[str, np.ndarray]
    grid: dict[str, dict[str, Any]]

    @property
    def n_nodes(self) -> int:
        return int(self.lat.shape[0])

    @property
    def n_edges(self) -> int:
        return int(self.eu.shape[0])


_RAIL_CACHE: dict[str, RailGraph | None] = {}


def load_rail_graph(path: str | None = None, *, log: Any = None) -> RailGraph | None:
    path = os.path.abspath(
        path or os.environ.get("RAIL_GRAPH_PATH") or _default_path()
    )
    if path in _RAIL_CACHE:
        return _RAIL_CACHE[path]
    if not os.path.exists(path):
        if log:
            log.warning(
                "rail geometry: no graph at %s; rail legs fall back to cached "
                "geometry or a straight line. Build it with: "
                "python src/backend/tool/build_rail_graph.py",
                path,
            )
        _RAIL_CACHE[path] = None
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
        # Read every array INSIDE the with-block. NpzFile lazily opens members,
        # so touching z["eflags"] after the archive is closed raises
        # AttributeError: 'NoneType' object has no attribute 'open'.
        flags = z["eflags"] if "eflags" in z.files else None

    n = int(lat.shape[0])
    csr_off: dict[str, np.ndarray] = {}
    csr_edge: dict[str, np.ndarray] = {}
    speed_mps: dict[str, np.ndarray] = {}
    grid: dict[str, dict[str, Any]] = {}
    order = np.argsort(eu, kind="stable")

    # One profile per OSM class. All classes share the topology; the filter is
    # just which bits are set. "all" keeps every edge.
    profiles = {"all": MODE_RAIL | MODE_LIGHT | MODE_TRAM}
    for cls, bit in (("rail", MODE_RAIL), ("light_rail", MODE_LIGHT), ("tram", MODE_TRAM)):
        profiles[cls] = bit

    for name, bit in profiles.items():
        if flags is None:
            usable = espec[:, 0] > 0
        else:
            # bool() matters: uint8 & bit stays uint8 and would be used as an
            # integer index, not a mask.
            usable = ((flags & np.uint8(bit)) != 0) & (espec[:, 0] > 0)
        kept = order[usable[order]]
        deg = np.bincount(eu[kept], minlength=n).astype(np.int64)
        off = np.zeros(n + 1, dtype=np.int64)
        np.cumsum(deg, out=off[1:])
        csr_off[name] = off
        csr_edge[name] = kept.astype(np.int32)
        speed_mps[name] = (espec[:, 0] / 10.0).astype(np.float32)
        grid[name] = _build_grid(np.nonzero(deg > 0)[0], lat, lon, GRID_CELL_DEG)

    g = RailGraph(
        lat=lat, lon=lon, eu=eu, ev=ev, elen=elen, espec=espec,
        ename=ename, names=names, csr_off=csr_off, csr_edge=csr_edge,
        speed_mps=speed_mps, grid=grid,
    )
    _RAIL_CACHE[path] = g
    if log:
        log.info(
            "rail geometry: %s loaded in %.1fs (%d nodes, %d edges)",
            os.path.basename(path), time.time() - t0, g.n_nodes, g.n_edges,
        )
    return g


def _snap(g: RailGraph, profile: str, lat: float, lon: float,
          max_m: float = RAIL_SNAP_M) -> tuple[int, float] | None:
    """Nearest track node for `profile`, within max_m."""
    idx = g.grid.get(profile)
    if idx is None:
        return None
    cell, lat0, lon0 = idx["cell"], idx["lat0"], idx["lon0"]
    n_lat, n_lon = idx["n_lat"], idx["n_lon"]
    ci = min(max(int((lat - lat0) / cell), 0), n_lat - 1)
    cj = min(max(int((lon - lon0) / cell), 0), n_lon - 1)
    max_ring = int(max_m / 111_320.0 / cell) + 1
    best: tuple[int, float] | None = None
    for ring in range(0, max_ring + 1):
        if best is not None and ring * cell * 111_320.0 > best[1]:
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
        d = _dist_to(g, cand, lat, lon)
        k = int(np.argmin(d))
        node = int(cand[k])
        h = haversine_m(lat, lon, float(g.lat[node]), float(g.lon[node]))
        if h <= max_m and (best is None or h < best[1]):
            best = (node, h)
    return best


def _astar(g: RailGraph, profile: str, src: int, dst: int) -> tuple[list[int], float] | None:
    edge_ids = g.csr_edge[profile]
    off = g.csr_off[profile]
    eu, ev, elen, spd = g.eu, g.ev, g.elen, g.speed_mps[profile]

    lat0, lon0 = float(g.lat[src]), float(g.lon[src])
    dlat = (g.lat - lat0) * 111_320.0
    dlon = (g.lon - lon0) * 111_320.0 * max(math.cos(math.radians(lat0)), 1e-6)
    max_spd = max(float(spd[edge_ids].max()) if edge_ids.size else 1.0, 0.1)
    crow = math.hypot(float(dlat[dst]), float(dlon[dst]))
    min_spd = max(float(spd[edge_ids].min()) if edge_ids.size else 1.0, 0.1)
    cost_cap = (crow / min_spd) * UNREACHABLE_COST_FACTOR

    n = g.n_nodes
    g_score = np.full(n, np.inf, dtype=np.float64)
    came = np.full(n, -1, dtype=np.int64)
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
            while came[cur] != -1:
                e = int(came[cur])
                edges.append(e)
                cur = int(eu[e])
            edges.reverse()
            return edges, float(g_score[dst])
        expanded += 1
        if expanded > MAX_EXPAND_NODES or f > cost_cap:
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
                came[nxt] = eid
                h = math.hypot(float(dlat[nxt]), float(dlon[nxt])) / max_spd
                heapq.heappush(heap, (cost + h, nxt))
    return None


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
    g: RailGraph,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    profile: str = "all",
    max_snap_m: float = RAIL_SNAP_M,
) -> RailTrack | None:
    """The real track polyline between two points, or None if none connects.

    None means the points are not on the same connected track (a branch, a
    freight-only line, or genuinely no rail nearby). The caller must then fall
    back -- and must never substitute a straight line and call it a rail path.
    """
    if profile not in g.csr_edge:
        profile = "all"
    sa = _snap(g, profile, a_lat, a_lon, max_snap_m)
    sb = _snap(g, profile, b_lat, b_lon, max_snap_m)
    if sa is None or sb is None:
        return None
    src, dst = sa[0], sb[0]
    if src == dst:
        return RailTrack(
            geometry=[[a_lat, a_lon], [b_lat, b_lon]],
            distance_m=haversine_m(a_lat, a_lon, b_lat, b_lon),
            snapped_from=(float(g.lat[src]), float(g.lon[src])),
            snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
            snap_from_m=sa[1],
            snap_to_m=sb[1],
        )
    found = _astar(g, profile, src, dst)
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

    length = 0.0
    for i in range(len(pts) - 1):
        length += haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
    return RailTrack(
        geometry=pts,
        distance_m=length,
        snapped_from=(float(g.lat[src]), float(g.lon[src])),
        snapped_to=(float(g.lat[dst]), float(g.lon[dst])),
        snap_from_m=sa[1],
        snap_to_m=sb[1],
        classes=classes,
    )


_RAIL_MEMO: dict[tuple, "RailTrack | None"] = {}


def track_between_cached(
    g: RailGraph, a_lat: float, a_lon: float, b_lat: float, b_lon: float,
    profile: str = "all", max_snap_m: float = RAIL_SNAP_M,
) -> RailTrack | None:
    key = (f"{a_lat:.5f},{a_lon:.5f}", f"{b_lat:.5f},{b_lon:.5f}", profile, str(id(g)))
    if key in _RAIL_MEMO:
        return _RAIL_MEMO[key]
    t = track_between(g, a_lat, a_lon, b_lat, b_lon, profile, max_snap_m)
    if len(_RAIL_MEMO) >= 4096:
        _RAIL_MEMO.clear()
    _RAIL_MEMO[key] = t
    return t