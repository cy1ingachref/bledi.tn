"""Nearest-node snapping and A* over a CSR graph of roads or tracks.

Both networks are millions of nodes, so they are flat numpy arrays (one node
table, one directed edge table) plus, per profile, a CSR index of usable edges
and a uniform grid of nodes that can start a move.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bledi_transit.domain.geo import haversine_m

M_PER_DEG = 111_320.0
# Snap-index cell size in degrees (~2.2 km N-S at Tunisia's latitude).
GRID_CELL_DEG = 0.02
# How far past the straight-line travel time a search may go before the pair
# is declared unreachable. Without it an unreachable pair exhausts its whole
# component (measured 10.7 s each). A multiple, so a real detour around a
# mountain or a one-way pair is never cut off.
UNREACHABLE_COST_FACTOR = 25.0


@dataclass(slots=True, eq=False)
class Graph:
    lat: np.ndarray
    lon: np.ndarray
    eu: np.ndarray
    ev: np.ndarray
    elen: np.ndarray
    ename: np.ndarray
    names: list[tuple[str, ...]]
    csr_off: dict[str, np.ndarray] = field(default_factory=dict)
    csr_edge: dict[str, np.ndarray] = field(default_factory=dict)
    speed_mps: dict[str, np.ndarray] = field(default_factory=dict)
    grid: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Undirected component label per node, when the build computed one.
    comp: dict[str, np.ndarray | None] = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return int(self.lat.shape[0])

    @property
    def n_edges(self) -> int:
        return int(self.eu.shape[0])

    def add_profile(self, name: str, order: np.ndarray, usable: np.ndarray, speed_mps: np.ndarray) -> None:
        """Index the usable edges of one profile. `order` is argsort(eu), shared across profiles."""
        kept = order[usable[order]]
        deg = np.bincount(self.eu[kept], minlength=self.n_nodes).astype(np.int64)
        off = np.zeros(self.n_nodes + 1, dtype=np.int64)
        np.cumsum(deg, out=off[1:])
        self.csr_off[name] = off
        self.csr_edge[name] = kept.astype(np.int32)
        self.speed_mps[name] = speed_mps
        self.grid[name] = _build_grid(np.nonzero(deg > 0)[0], self.lat, self.lon, GRID_CELL_DEG)


def _build_grid(src_nodes: np.ndarray, lat: np.ndarray, lon: np.ndarray, cell: float) -> dict[str, Any]:
    """Counting sort by cell id: cell c owns nodes[off[c]:off[c + 1]]."""
    lat0 = float(lat.min())
    lon0 = float(lon.min())
    n_lat = int(np.floor((float(lat.max()) - lat0) / cell)) + 1
    n_lon = int(np.floor((float(lon.max()) - lon0) / cell)) + 1
    i = np.clip(((lat[src_nodes] - lat0) / cell).astype(np.int64), 0, n_lat - 1)
    j = np.clip(((lon[src_nodes] - lon0) / cell).astype(np.int64), 0, n_lon - 1)
    flat = i * n_lon + j
    order = np.argsort(flat, kind="stable")
    n_cells = n_lat * n_lon
    counts = np.bincount(flat[order], minlength=n_cells)
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


def snap_candidates(
    g: Graph, profile: str, lat: float, lon: float, max_m: float, want: int
) -> list[tuple[int, float]]:
    """Up to `want` usable nodes within `max_m`, nearest first, with their distance.

    More than one because the nearest node can sit on an unconnected stub: a
    station 125 m from its destination snapped onto a dead-end foot path while
    the second nearest node, 30 m further, was on a through street.
    """
    idx = g.grid.get(profile)
    if idx is None:
        return []
    cell, lat0, lon0 = idx["cell"], idx["lat0"], idx["lon0"]
    n_lat, n_lon = idx["n_lat"], idx["n_lon"]
    ci = min(max(int((lat - lat0) / cell), 0), n_lat - 1)
    cj = min(max(int((lon - lon0) / cell), 0), n_lon - 1)
    max_ring = int(max_m / M_PER_DEG / cell) + 1

    seen: dict[int, float] = {}
    for ring in range(0, max_ring + 1):
        # Any node in ring >= r + 1 lies at least r cells away, so once the
        # best hit beats that, nothing further out can win.
        if seen and ring * cell * M_PER_DEG > min(seen.values()):
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
        for node in cand.tolist():
            h = haversine_m(lat, lon, float(g.lat[node]), float(g.lon[node]))
            if h <= max_m and (node not in seen or h < seen[node]):
                seen[node] = h
    return sorted(seen.items(), key=lambda nd: nd[1])[:want]


def astar(g: Graph, profile: str, src: int, dst: int, max_expand: int) -> tuple[list[int], float] | None:
    """A* on travel time. Returns (edge ids along the path, seconds) or None."""
    edge_ids = g.csr_edge[profile]
    off = g.csr_off[profile]
    eu, ev, elen, spd = g.eu, g.ev, g.elen, g.speed_mps[profile]

    lat_d, lon_d = float(g.lat[dst]), float(g.lon[dst])
    lon_scale = M_PER_DEG * max(math.cos(math.radians(lat_d)), 1e-6)

    def to_dst_m(node: int) -> float:
        return math.hypot((float(g.lat[node]) - lat_d) * M_PER_DEG, (float(g.lon[node]) - lon_d) * lon_scale)

    # Straight line to the destination over the fastest speed anywhere cannot
    # overestimate, so A* stays optimal.
    max_spd = max(float(spd[edge_ids].max()) if edge_ids.size else 1.0, 0.1)
    min_spd = max(float(spd[edge_ids].min()) if edge_ids.size else 0.1, 0.1)
    cost_cap = (to_dst_m(src) / min_spd) * UNREACHABLE_COST_FACTOR

    n = g.n_nodes
    g_score = np.full(n, np.inf, dtype=np.float64)
    # The edge used to reach each node, not the parent node, so the path keeps
    # each edge's way name.
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
                heapq.heappush(heap, (cost + to_dst_m(nxt) / max_spd, nxt))
    return None
