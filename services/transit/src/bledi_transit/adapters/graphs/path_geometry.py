"""PathGeometry over the OSM road and rail graphs."""
from __future__ import annotations

import logging
from pathlib import Path

from bledi_transit.adapters.graphs.rail_graph import load_rail_graph, track_between_cached
from bledi_transit.adapters.graphs.road_graph import load_graph, road_route_cached
from bledi_transit.adapters.graphs.search import Graph, snap_candidates
from bledi_transit.application.ports import Polyline

log = logging.getLogger("bledi.routing")


class GraphPathGeometry:
    def __init__(self, road: Graph | None, rail: Graph | None) -> None:
        self._road = road
        self._rail = rail

    @classmethod
    def load(cls, road_path: Path, rail_path: Path) -> GraphPathGeometry:
        """A missing graph file leaves that network unserved; legs fall back to cached geometry."""
        return cls(load_graph(str(road_path), log=log), load_rail_graph(str(rail_path), log=log))

    def road(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float, mode: str) -> tuple[Polyline, float] | None:
        if self._road is None:
            return None
        try:
            r = road_route_cached(self._road, a_lat, a_lon, b_lat, b_lon, mode)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("road routing failed for %s -> %s: %s", (a_lat, a_lon), (b_lat, b_lon), exc)
            return None
        if r is None or len(r.geometry) < 2:
            return None
        return r.geometry, r.distance_m

    def rail(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> tuple[Polyline, float] | None:
        """Snaps both points onto the nearest track, so the answer follows the rails, not line numbers."""
        if self._rail is None:
            return None
        try:
            t = track_between_cached(self._rail, a_lat, a_lon, b_lat, b_lon)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("rail geometry failed for %s -> %s: %s", (a_lat, a_lon), (b_lat, b_lon), exc)
            return None
        if t is None or len(t.geometry) < 2:
            return None
        return t.geometry, t.distance_m

    def foot_bridges(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> list[Polyline]:
        g = self._road
        if g is None:
            return []
        out: list[Polyline] = []
        try:
            a_candidates = snap_candidates(g, "foot", a_lat, a_lon, max_m=250.0, want=3)
            b_candidates = snap_candidates(g, "foot", b_lat, b_lon, max_m=250.0, want=3)
            for a_node, _ in a_candidates:
                for b_node, _ in b_candidates:
                    if a_node == b_node:
                        continue
                    a_pt = [float(g.lat[a_node]), float(g.lon[a_node])]
                    b_pt = [float(g.lat[b_node]), float(g.lon[b_node])]
                    r = road_route_cached(g, *a_pt, *b_pt, "foot", max_snap_m=1.0)
                    if r is None or len(r.geometry) < 2:
                        continue
                    full = [[a_lat, a_lon], a_pt, *r.geometry, b_pt, [b_lat, b_lon]]
                    deduped = [full[0]]
                    for pt in full[1:]:
                        if pt != deduped[-1]:
                            deduped.append(pt)
                    out.append(deduped)
        except Exception:
            return []
        return out
