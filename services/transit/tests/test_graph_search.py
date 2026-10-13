from __future__ import annotations

import numpy as np

from bledi_transit.adapters.graphs.search import M_PER_DEG, Graph, astar

STEP_DEG = 0.001
SPOKE = 5


def star() -> tuple[Graph, int]:
    """A center with four spokes of SPOKE nodes each, edges both ways. Returns the graph and
    the far end of the east spoke."""
    lat, lon = [0.0], [0.0]
    eu: list[int] = []
    ev: list[int] = []
    for dlat, dlon in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        prev = 0
        for k in range(1, SPOKE + 1):
            lat.append(dlat * k * STEP_DEG)
            lon.append(dlon * k * STEP_DEG)
            node = len(lat) - 1
            eu += [prev, node]
            ev += [node, prev]
            prev = node
    n_edges = len(eu)
    g = Graph(
        lat=np.array(lat),
        lon=np.array(lon),
        eu=np.array(eu, dtype=np.int64),
        ev=np.array(ev, dtype=np.int64),
        elen=np.full(n_edges, STEP_DEG * M_PER_DEG),
        ename=np.zeros(n_edges, dtype=np.int32),
        names=[()],
    )
    g.add_profile("car", np.argsort(g.eu, kind="stable"), np.ones(n_edges, dtype=bool), np.full(n_edges, 10.0))
    return g, SPOKE


def test_finds_the_shortest_path() -> None:
    g, east_end = star()
    edges, seconds = astar(g, "car", 0, east_end, max_expand=1000)
    assert len(edges) == SPOKE
    assert abs(seconds - SPOKE * STEP_DEG * M_PER_DEG / 10.0) < 1e-6


def test_heads_for_the_destination() -> None:
    # Guided toward the destination, the search walks the east spoke and barely touches the
    # other three. Guided away from the source instead, it expands nearly the whole star first.
    g, east_end = star()
    assert astar(g, "car", 0, east_end, max_expand=SPOKE + 2) is not None
