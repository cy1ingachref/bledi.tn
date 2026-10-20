"""Multi-modal transit search over the stop graph (Dijkstra).

Physical cost model only: ride time (per-mode average speed) + expected wait
(paid once per boarding = half the headway when departures exist, else a
per-mode default) + transfer penalty + walk time.

dist/prev are keyed by (station_id, line_arrived_on) so a cheap arrival on a
dead-end line can never permanently shadow a slightly-pricier arrival on the
line that continues penalty-free. Wait is charged once at boarding
(cur_line != ln_id), not at every stop. The line actually used for each segment
is the one stored during relaxation, not a post-hoc heuristic (which
misattributes shared corridor edges).
"""

from __future__ import annotations

import heapq
import logging
from collections import defaultdict
from typing import Any

from bledi_transit.application.ports import PathGeometry
from bledi_transit.application.routing.graph import (
    Edge,
    Segments,
    add_louage_taxi_transfers,
    add_walk_edges,
    line_edge,
)
from bledi_transit.application.routing.itinerary import expand_path
from bledi_transit.application.routing.legs import NoPathGeometry, road_geometry_for
from bledi_transit.application.routing.planner import plan
from bledi_transit.domain.fares import FARE_DINARS
from bledi_transit.domain.geo import haversine_m, polyline_length
from bledi_transit.domain.modes import BUS_MODES, MODE_LABELS_FR, TAXI_MODES, canonical_mode
from bledi_transit.domain.timetable import expected_wait
from bledi_transit.domain.tunables import (
    BOARDING_WAIT_CAP,
    DROP_OFF_CANDIDATES,
    DROPOFF_SEARCH_METERS,
    MAX_END_WALK_METERS,
    MAX_START_WALK_METERS,
    MAX_WALK_EDGE_METERS,
    TAXI_MIN_DISTANCE_M,
    TAXI_SPEED_MS,
    TRANSFER_PENALTY_SEC,
    WALK_SPEED_MS,
)

log = logging.getLogger("bledi.routing")


class Router:
    """The stop graph and the search over it.

    The geometry caches and live paths only decide what each edge and leg is
    drawn with and how long it really is; without them every leg is costed on
    the straight line.
    """

    def __init__(
            self,
            stations: dict[str, dict[str, Any]],
            lines: list[dict[str, Any]],
            *,
            segments: Segments | None = None,
            walk_segments: Segments | None = None,
            taxi_segments: dict[str, Any] | None = None,
            paths: PathGeometry | None = None,
            max_walk_edge_m: float = MAX_WALK_EDGE_METERS,
            louage_stations: list[dict[str, Any]] | None = None,
        ) -> None:
        self.stations = stations
        self.lines = lines
        self.taxi_geometry = taxi_segments or {}
        self.paths: PathGeometry = paths or NoPathGeometry()
        self.mode_of_line: dict[str, str] = {}
        # mode_of_line keeps the raw seed value because allowed_modes holds raw
        # seed modes. The canonical form is what labels, fares and the API report.
        self.user_mode_of_line: dict[str, str] = {}
        self.line_wait: dict[str, float] = {}  # line_id -> boarding wait (s)
        for ln in lines:
            ln_id = ln.get("id", "") or ""
            mode = ln.get("mode", "bus") or "bus"
            self.mode_of_line[ln_id] = mode
            self.user_mode_of_line[ln_id] = canonical_mode(mode)
            self.line_wait[ln_id] = min(expected_wait(ln.get("departures"), mode), BOARDING_WAIT_CAP)
        # From the lines' stop arrays, not the station's lines_served fragments,
        # which are direction-oriented and often lack route_short_name.
        self.lines_by_station: dict[str, list[str]] = defaultdict(list)
        for ln in lines:
            ln_id = ln.get("id", "") or ""
            if not ln_id:
                continue
            for sid in ln.get("stations") or ln.get("stops") or []:
                if isinstance(sid, str):
                    self.lines_by_station[sid].append(ln_id)
        self.adj: dict[str, list[Edge]] = defaultdict(list)
        segments = segments or {}
        for ln in lines:
            stops = ln.get("stations") or ln.get("stops") or []
            if len(stops) < 2:
                continue
            ln_id = ln.get("id", "") or ""
            if not ln_id:
                continue
            mode = self.mode_of_line.get(ln_id, "bus") or "bus"
            wait_s = self.line_wait.get(ln_id, 0.0)
            for i in range(len(stops) - 1):
                a, b = stops[i], stops[i + 1]
                sa = self.stations.get(a)
                sb = self.stations.get(b)
                if not sa or not sb:
                    continue
                if not sa.get("lat") or not sa.get("lon") or not sb.get("lat") or not sb.get("lon"):
                    continue
                self.adj[a].append(line_edge(segments, a, b, sa, sb, ln_id, mode, wait_s))
                self.adj[b].append(line_edge(segments, b, a, sb, sa, ln_id, mode, wait_s))
        add_walk_edges(self.adj, self.stations, walk_segments or {}, max_walk_edge_m)
        # Connect louage and taxi stations as transfer hubs.
        add_louage_taxi_transfers(self.adj, self.stations, louage_stations)

    route_plan = plan

    def route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        allowed_modes: frozenset[str] | None = None,
        transfer_penalty_sec: float | None = None,
        max_walk_m: float | None = None,
    ) -> dict[str, Any]:
        """Find the best itinerary for one mode set and transfer penalty.

        Returns the transit itinerary when one exists, with a direct taxi as an
        alternative; otherwise a direct taxi when permitted; otherwise the
        direct walk.

        Uses a single multi-source Dijkstra from all start candidates (with the
        walk-to-station cost as the initial label) so one pass covers every
        (start, end) pair instead of N*M separate Dijkstras.
        """
        transfer_penalty = (
            TRANSFER_PENALTY_SEC
            if transfer_penalty_sec is None
            else float(transfer_penalty_sec)
        )
        start_cap = MAX_START_WALK_METERS if max_walk_m is None else float(max_walk_m)
        end_cap = MAX_END_WALK_METERS if max_walk_m is None else float(max_walk_m)
        # Expand START walk radius for bus-restricted searches to ensure the origin
        # can reach a bus stop. Do NOT expand end_cap unconditionally - that would
        # make stations near the origin become end candidates, producing fake
        # "bus then taxi" paths when the destination has no bus service.
        if allowed_modes is not None and (allowed_modes & BUS_MODES):
            start_cap = max(start_cap, MAX_START_WALK_METERS * 20)
        start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)
        end_candidates = self._nearest_stations(end_lat, end_lon, end_cap)
        # A bus-restricted search needs at least one start station with a bus edge.
        if allowed_modes is not None and (allowed_modes & BUS_MODES):
            def has_bus_edge(st_id):
                return any(e.mode in BUS_MODES for e in self.adj.get(st_id, []))
            if not any(has_bus_edge(sc['id']) for sc in start_candidates):
                start_cap = MAX_START_WALK_METERS * 500
                start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)

        # No stop to walk to: a town with no station of its own still gets a
        # ride then a final gap, instead of one taxi line across the country.
        # Only served stops help; see DROP_OFF_CANDIDATES for the count.
        if not end_candidates and end_cap >= MAX_END_WALK_METERS:
            served = [
                s
                for s in self._nearest_stations(end_lat, end_lon, DROPOFF_SEARCH_METERS)
                if any(e.mode != "walk" for e in self.adj.get(s["id"], ()))
            ]
            if served:
                end_candidates = served[:DROP_OFF_CANDIDATES]
        end_ids = {ec["id"] for ec in end_candidates}

        best: dict[str, Any] | None = None
        best_cost = float("inf")

        direct_m = haversine_m(start_lat, start_lon, end_lat, end_lon)
        direct_walk_s = direct_m / WALK_SPEED_MS
        if allowed_modes is None or "walk" in allowed_modes:
            best = {
                "mode": "walk",
                "duration_min": round(direct_walk_s / 60, 1),
                "walk_m": round(direct_m),
                "fare_dinars": None,
                "steps": [
                    {
                        "type": "walk",
                        "from": {"lat": start_lat, "lon": start_lon},
                        "to": {"lat": end_lat, "lon": end_lon},
                        "distance_m": round(direct_m),
                        "duration_min": round(direct_walk_s / 60, 1),
                        "label": f"Marcher {round(direct_m)} m (~{round(direct_walk_s / 60)} min)",
                    }
                ],
            }
            best_cost = direct_walk_s

        # Walking-only request: the user asked for directions on foot, so no
        # transit search and no vehicle fallback should run.
        if allowed_modes is not None and not (allowed_modes - {"walk"}):
            return best

        if start_candidates and end_candidates:
            dist: dict[tuple[str, str | None], float] = {}
            prev: dict[tuple[str, str | None], tuple[str, str | None] | None] = {}
            pq: list[tuple[float, str, str]] = []
            for sc in start_candidates:
                sid = sc["id"]
                walk_s = sc["_dist_m"] / WALK_SPEED_MS
                state: tuple[str, str | None] = (sid, None)
                dist[state] = walk_s
                prev[state] = None
                heapq.heappush(pq, (walk_s, sid, ""))

            visited: set[tuple[str, str | None]] = set()
            while pq:
                cost, cur, _tie = heapq.heappop(pq)
                # The heap stores "" for "no line": costs tie constantly in the
                # walk network, and comparing None with a str raises TypeError.
                cur_line = _tie or None
                if cost >= best_cost:
                    break
                state = (cur, cur_line)
                if state in visited:
                    continue
                visited.add(state)

                if cur in end_ids:
                    ec = self.stations.get(cur)
                    if ec and ec.get("lat") and ec.get("lon"):
                        end_walk_m = haversine_m(ec["lat"], ec["lon"], end_lat, end_lon)
                        # A gap past MAX_END_WALK_METERS is a taxi hop. Distance
                        # alone decides, here and in expand_path, so the cost and
                        # the drawn leg agree.
                        if end_walk_m > MAX_END_WALK_METERS:
                            end_walk_s = end_walk_m / TAXI_SPEED_MS
                        else:
                            end_walk_s = end_walk_m / WALK_SPEED_MS
                        total_s = cost + end_walk_s
                        if total_s < best_cost:
                            path_stations, path_lines = self._reconstruct(prev, state)
                            total_min, steps = expand_path(
                                self,
                                path_stations,
                                path_lines,
                                start_lat, start_lon,
                                end_lat, end_lon,
                                self.stations.get(path_stations[0]) if path_stations else None,
                                ec,
                                allowed_modes,
                            )
                            best = {
                                "mode": "transit",
                                "duration_min": total_min,
                                "steps": steps,
                                "fare_dinars": None,
                            }
                            best_cost = total_s

                if not self.stations.get(cur):
                    continue
                for edge in self.adj.get(cur, ()):
                    # Walking is always permitted: every option starts and ends
                    # on foot, and it is the only way to reach a stop the
                    # restricted network does not serve.
                    if (
                        allowed_modes is not None
                        and edge.mode != "walk"
                        and edge.mode not in allowed_modes
                    ):
                        continue
                    is_walk = edge.mode == "walk"
                    arrived_line = None if is_walk else edge.line
                    segment_cost = edge.time_s
                    if not is_walk:
                        if cur_line != edge.line:
                            segment_cost += edge.wait_s
                        if cur_line is not None and cur_line != edge.line:
                            segment_cost += transfer_penalty
                    new_cost = cost + segment_cost
                    new_state: tuple[str, str | None] = (edge.to_id, arrived_line)
                    if new_cost < dist.get(new_state, float("inf")):
                        dist[new_state] = new_cost
                        prev[new_state] = state
                        heapq.heappush(pq, (new_cost, edge.to_id, arrived_line or ""))

        # A direct taxi is only an alternative when transit exists, or one taxi
        # line would replace every transit route it beats on time. It also needs
        # taxi or louaj in the mode selection.
        have_transit = best is not None and best.get("mode") == "transit"
        direct_km = direct_m / 1000.0
        taxi_permitted = allowed_modes is None or bool(
            allowed_modes & TAXI_MODES
        )
        # Louage and taxi are priced differently (shared per seat vs metered
        # private hire), so the leg is labelled and costed as whichever the
        # user actually selected. When both are allowed, taxi is the more
        # general answer and keeps its own label.
        road_mode = "taxi"
        if allowed_modes is not None and "taxi" not in allowed_modes and "louaj" in allowed_modes:
            road_mode = "louaj"
        road_speed_ms = TAXI_SPEED_MS
        def road_fare_for(km: float) -> float:
            base, per_km = FARE_DINARS[road_mode]
            return base + per_km * km
        if have_transit:
            taxi_s = direct_m / TAXI_SPEED_MS
            if direct_km * 1000 >= TAXI_MIN_DISTANCE_M:
                taxi_fare = road_fare_for(direct_km)
                road_label = MODE_LABELS_FR.get(road_mode, road_mode.capitalize())
                best["alternatives"] = best.get("alternatives", []) + [{
                    "mode": road_mode,
                    "duration_min": round(taxi_s / 60, 1),
                    "distance_km": round(direct_km, 1),
                    "fare_dinars": round(taxi_fare, 2),
                    "label": f"{road_label} direct - {round(direct_km, 1)} km (~{round(taxi_s / 60)} min, {round(taxi_fare, 2)} DT)",
                }]
        elif taxi_permitted and direct_km * 1000 >= TAXI_MIN_DISTANCE_M:
            # Cost the trip on the same real road distance the leg is drawn
            # with: live road graph first, precomputed taxi cache second.
            # Pricing the straight line and drawing the road would make the
            # option look faster than the polyline the user sees.
            live_taxi = self.paths.road(start_lat, start_lon, end_lat, end_lon, "car")
            if live_taxi is not None and live_taxi[1] >= 0.95 * direct_m:
                taxi_road_m = live_taxi[1]
            else:
                taxi_geom_pre = road_geometry_for(
                    self.taxi_geometry, start_lat, start_lon, end_lat, end_lon
                )
                taxi_road_m = (
                    polyline_length(taxi_geom_pre)
                    if taxi_geom_pre and polyline_length(taxi_geom_pre) >= 0.95 * direct_m
                    else direct_m
                )
            taxi_s = taxi_road_m / road_speed_ms
            taxi_fare = road_fare_for(direct_km)
            if taxi_s < best_cost:
                taxi_geom: list[list[float]] = []
                if live_taxi is not None and live_taxi[1] >= 0.95 * direct_m:
                    taxi_geom, road_m = live_taxi[0], live_taxi[1]
                else:
                    cached = road_geometry_for(
                        self.taxi_geometry, start_lat, start_lon, end_lat, end_lon
                    )
                    road_m = polyline_length(cached) if cached else direct_m
                    if cached and road_m >= 0.95 * direct_m:
                        taxi_geom = cached
                    else:
                        road_m = direct_m
                road_s = road_m / road_speed_ms
                road_fare = road_fare_for(road_m / 1000.0)
                taxi_step = {
                    "type": road_mode,
                    "mode": road_mode,
                    "from": {"lat": start_lat, "lon": start_lon},
                    "to": {"lat": end_lat, "lon": end_lon},
                    "from_id": None,
                    "to_id": None,
                    "distance_km": round(road_m / 1000, 2),
                    "distance_m": round(road_m),
                    "straight_m": round(direct_m),
                    "duration_min": round(road_s / 60, 1),
                    "time_seconds": round(road_s, 1),
                    "geometry": taxi_geom,
                    "fare_dinars": round(road_fare, 2),
                    "label": (
                        f"{MODE_LABELS_FR.get(road_mode, road_mode.capitalize())} — "
                        f"{round(road_m / 1000, 1)} km (~{round(road_s / 60)} min, {round(road_fare, 2)} DT)"
                    ),
                }
                best = {
                    "mode": road_mode,
                    "duration_min": round(taxi_s / 60, 1),
                    "steps": [taxi_step],
                    "fare_dinars": round(taxi_fare, 2),
                }

        if not best:
            return {"error": "No route found", "duration_min": 0, "steps": [], "fare_dinars": None}
        best["duration_min"] = round(best["duration_min"], 1)
        return best

    def edge_between(self, a_id: str, b_id: str, line: str | None) -> Edge | None:
        """The graph edge actually traversed from a_id to b_id on `line`.

        Several lines can share a corridor between the same two stops, so the
        line is part of the match. Falls back to any a->b edge when the line is
        unknown, which keeps step building working for a path whose line
        context was lost.
        """
        for e in self.adj.get(a_id, ()):
            if e.to_id != b_id:
                continue
            if line is None or e.line == line or e.mode == "walk":
                return e
        return None

    @staticmethod
    def _reconstruct(
        prev: dict[tuple[str, str | None], tuple[str, str | None] | None],
        state: tuple[str, str | None],
    ) -> tuple[list[str], list[str | None]]:
        """Walk `prev` back to the source and return (stations, lines)."""
        stations: list[str] = []
        lines: list[str | None] = []
        node: tuple[str, str | None] | None = state
        while node is not None:
            stations.append(node[0])
            lines.append(node[1])
            node = prev.get(node)
        stations.reverse()
        lines.reverse()
        return stations, lines

    def _nearest_stations(
        self, lat: float, lon: float, max_m: float
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self.stations.values():
            if not s.get("lat") or not s.get("lon"):
                continue
            d = haversine_m(lat, lon, s["lat"], s["lon"])
            if d <= max_m:
                out.append({**s, "_dist_m": d})
        out.sort(key=lambda x: x["_dist_m"])
        return out
