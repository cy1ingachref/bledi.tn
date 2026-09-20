#!/usr/bin/env python3
"""Tunismapper-style multi-modal routing engine for bledi.tn.

Architecture:
- Stations = graph nodes (with lat/lon)
- Transit lines = pre-built edges between consecutive stations
- Walk = edges between any two stations within walk_distance_m
- Dijkstra finds shortest path from start to destination
- Cost function: transit_cost + transfer_penalty + walk_time

Key design:
- Dual-speed model: transit edges have a high "routing cost speed" so transit
  is heavily preferred over walking (matching tunismapper behavior), but the
  user-facing display time uses realistic bus speed (~22 km/h).
- Per-segment overhead: dwell time + headway added to each transit segment
  cost so transfers between lines become relatively cheaper than many small segments.
- Transfer penalties when switching lines.

Tuned to produce reasonable results for urban trips in Tunis area.
"""
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

BASE = Path(r"C:\Users\cy1in\Downloads\TunisiaTransport")
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"

# Walking speed
WALK_SPEED_KMH = 4.5
WALK_SPEED_MS = WALK_SPEED_KMH / 3.6  # 1.25 m/s

# Transit "cost speed" for routing decisions — high ratio makes transit preferred
# Tunismapper uses non-physical cost (effective ~960:1 vs walking); we approximate
# with a cost speed that makes transit dominate for any station-accessible trip.
TRANSIT_COST_SPEED_MS = 3000.0  # ~2400:1 vs walking at 1.25 m/s

# Transit display speed (user-facing times) — realistic average bus speed
TRANSIT_DISPLAY_SPEED_KMH = 22.0
TRANSIT_DISPLAY_SPEED_MS = TRANSIT_DISPLAY_SPEED_KMH / 3.6  # ~6.11 m/s

# Taxi speed
TAXI_SPEED_KMH = 45.0
TAXI_SPEED_MS = TAXI_SPEED_KMH / 3.6  # 12.5 m/s

# Routing cost overheads
SEGMENT_OVERHEAD_SEC = 0.0        # no per-segment overhead — transit wins on distance alone
TRANSFER_ROUTING_PENALTY_SEC = 90.0  # per-transfer overhead

# Max walk distances
MAX_WALK_METERS = 1500
MAX_START_WALK_METERS = 2000
MAX_END_WALK_METERS = 2000


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def time_at_speed(distance_m: float, speed_ms: float) -> float:
    """Time in seconds to travel distance_m at speed_ms."""
    if speed_ms <= 0 or distance_m <= 0:
        return 0.0
    return distance_m / speed_ms


class RoutingGraph:
    """Graph of all stations and transit connections in Tunisia."""

    def __init__(self, seed: dict[str, Any]):
        self.stations: dict[str, dict] = {}
        self.edges: dict[str, list[dict]] = defaultdict(list)
        self.lines: dict[str, list[str]] = {}
        self.station_lines: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._build(seed)

    def _build(self, seed: dict[str, Any]) -> None:
        """Build the routing graph from the seed data."""
        # Stations
        for s in seed["stations"]:
            sid = s["id"]
            lat, lon = s.get("lat", 0), s.get("lon", 0)
            if lat and lon and lat != 0 and lon != 0:
                self.stations[sid.lower()] = {
                    "id": sid,
                    "name": s.get("name", sid),
                    "lat": lat,
                    "lon": lon,
                }

        # Lines
        for line in seed["lines"]:
            if "route_id" not in line:
                line["route_id"] = str(line.get("number", ""))
            number = str(line.get("number", ""))
            route_id = str(line.get("route_id", number))
            stops_raw = line.get("stations") or line.get("stops") or []

            # Flatten any nested lists
            stops: list = []
            for item in stops_raw:
                if isinstance(item, list):
                    stops.extend(item)
                else:
                    stops.append(item)

            if not stops:
                continue

            valid = [s.strip().lower() for s in stops
                     if isinstance(s, str) and s.strip().lower() in self.stations]
            if len(valid) < 2:
                continue

            line_key = route_id if route_id else number
            self.lines[line_key] = valid
            for sid in valid:
                self.station_lines[sid].append((number, line_key))

            # Transit edges: consecutive stops
            for i in range(len(valid) - 1):
                a, b = valid[i], valid[i + 1]
                dist = haversine(
                    self.stations[a]["lat"], self.stations[a]["lon"],
                    self.stations[b]["lat"], self.stations[b]["lon"],
                )
                # Routing cost: discounted transit speed + small overhead
                transit_cost = time_at_speed(dist, TRANSIT_COST_SPEED_MS)
                transit_cost += SEGMENT_OVERHEAD_SEC
                # Display time: realistic speed
                transit_display = time_at_speed(dist, TRANSIT_DISPLAY_SPEED_MS)

                for src, dst in ((a, b), (b, a)):
                    self.edges[src].append({
                        "to": dst,
                        "line": number,
                        "type": "transit",
                        "cost": transit_cost,              # routing cost
                        "display_time": transit_display,   # user display
                        "distance": dist,
                    })

    def station_sids_for_line(self, line_number: str) -> list[str]:
        """Return ordered station sids for a given line number."""
        # Try route_id keys first
        for stops in self.lines.values():
            for num, _ in self.station_lines.get(stops[0], []):
                if num == line_number:
                    return stops
        return self.lines.get(line_number, [])

    def lines_for_station(self, sid: str) -> list[tuple[str, str]]:
        """Return list of (line_number, route_id) for a station."""
        return self.station_lines.get(sid.lower(), [])

    def find_nearest(self, lat: float, lon: float,
                     max_m: float = MAX_START_WALK_METERS) -> tuple[str | None, float]:
        """Return (sid, distance_m) of nearest station within max_m."""
        best_sid, best_d = None, float("inf")
        for sid, s in self.stations.items():
            d = haversine(lat, lon, s["lat"], s["lon"])
            if d < best_d:
                best_d, best_sid = d, sid
        if best_d <= max_m:
            return (best_sid, best_d)
        return (None, best_d)

    def stations_within(self, lat: float, lon: float,
                        max_m: float = MAX_WALK_METERS) -> list[tuple[str, float]]:
        """Return sorted list of (sid, distance_m) within max_m."""
        result: list[tuple[str, float]] = []
        for sid, s in self.stations.items():
            d = haversine(lat, lon, s["lat"], s["lon"])
            if d <= max_m:
                result.append((sid, d))
        result.sort(key=lambda x: x[1])
        return result

    def add_walk_edges(self) -> int:
        """Add walk edges between all station pairs within walking distance."""
        count = 0
        sids = list(self.stations.keys())
        for i, sa_id in enumerate(sids):
            sa = self.stations[sa_id]
            for sb_id in sids[i + 1:]:
                sb = self.stations[sb_id]
                d = haversine(sa["lat"], sa["lon"], sb["lat"], sb["lon"])
                if d <= MAX_WALK_METERS:
                    wt = time_at_speed(d, WALK_SPEED_MS)
                    for src, dst in ((sa_id, sb_id), (sb_id, sa_id)):
                        self.edges[src].append({
                            "to": dst, "type": "walk",
                            "cost": wt, "display_time": wt,
                            "distance": d,
                        })
                    count += 1
        return count


class Router:
    """Multi-modal router using Dijkstra on the routing graph."""

    def __init__(self, graph: RoutingGraph):
        self.graph = graph

    def route(self, start_lat: float, start_lon: float,
              end_lat: float, end_lon: float) -> dict[str, Any]:
        """Find best route from (start_lat, start_lon) to (end_lat, end_lon).

        The returned dict has:
        - duration_min: user-facing duration in minutes
        - distance_m: total great-circle distance in meters
        - transfers: number of line changes
        - modes: list of mode strings (e.g. ["walk", "transit", "walk"])
        - steps: detailed per-segment step list
        - start_station / end_station: nearest boarding/alighting station ids
        - start_walk / end_walk: walk segment dicts (or None)
        """
        start_cands = self.graph.stations_within(
            start_lat, start_lon, MAX_START_WALK_METERS)
        end_cands = self.graph.stations_within(
            end_lat, end_lon, MAX_END_WALK_METERS)

        direct_dist = haversine(start_lat, start_lon, end_lat, end_lon)
        direct_walk = time_at_speed(direct_dist, WALK_SPEED_MS)
        direct_taxi = time_at_speed(direct_dist, TAXI_SPEED_MS)

        # Baseline: direct walk or taxi if no stations accessible
        best_cost = direct_walk
        best_result = {
            "duration_min": round(direct_walk / 60, 1),
            "distance_m": direct_dist,
            "transfers": 0,
            "modes": ["walk"],
            "steps": [{
                "type": "walk",
                "from_lat": start_lat, "from_lon": start_lon,
                "to_lat": end_lat, "to_lon": end_lon,
                "duration_s": direct_walk,
                "distance_m": direct_dist,
                "stop_name": "Trajet à pied",
            }],
            "path": [],
            "start_station": None,
            "end_station": None,
            "start_walk": None,
            "end_walk": None,
        }
        if direct_taxi < best_cost:
            best_cost = direct_taxi
            best_result = {
                "duration_min": round(direct_taxi / 60, 1),
                "distance_m": direct_dist,
                "transfers": 0,
                "modes": ["taxi"],
                "steps": [{
                    "type": "taxi",
                    "from_lat": start_lat, "from_lon": start_lon,
                    "to_lat": end_lat, "to_lon": end_lon,
                    "duration_s": direct_taxi,
                    "distance_m": direct_dist,
                    "stop_name": "Taxi direct",
                }],
                "path": [],
                "start_station": None,
                "end_station": None,
                "start_walk": None,
                "end_walk": None,
            }

        # Try all station-pair combinations
        for s_sid, s_dist in start_cands:
            s_walk = time_at_speed(s_dist, WALK_SPEED_MS)
            for e_sid, e_dist in end_cands:
                e_walk = time_at_speed(e_dist, WALK_SPEED_MS)
                res = self._dijkstra(s_sid, e_sid)
                if res.get("error"):
                    continue

                total_cost = s_walk + res["cost"] + e_walk
                if total_cost < best_cost:
                    best_cost = total_cost
                    steps = list(res["steps"])
                    if s_dist > 0:
                        steps.insert(0, {
                            "type": "walk",
                            "from_lat": start_lat, "from_lon": start_lon,
                            "to_lat": self.graph.stations[s_sid]["lat"],
                            "to_lon": self.graph.stations[s_sid]["lon"],
                            "duration_s": s_walk,
                            "distance_m": s_dist,
                            "stop_name": f"Walk to {self.graph.stations[s_sid]['name']}",
                        })
                    if e_dist > 0:
                        steps.append({
                            "type": "walk",
                            "from_lat": self.graph.stations[e_sid]["lat"],
                            "from_lon": self.graph.stations[e_sid]["lon"],
                            "to_lat": end_lat, "to_lon": end_lon,
                            "duration_s": e_walk,
                            "distance_m": e_dist,
                            "stop_name": f"Walk from {self.graph.stations[e_sid]['name']}",
                        })
                    total_display = s_walk + res["display"] + e_walk
                    best_result = {
                        "duration_min": round(total_display / 60, 1),
                        "distance_m": res["distance"] + s_dist + e_dist,
                        "transfers": res["transfers"],
                        "modes": self._merge_modes(steps),
                        "steps": steps,
                        "path": res["path"],
                        "start_station": s_sid,
                        "end_station": e_sid,
                        "start_walk": {
                            "distance_m": s_dist,
                            "duration_s": s_walk,
                            "from_lat": start_lat, "from_lon": start_lon,
                            "to_lat": self.graph.stations[s_sid]["lat"],
                            "to_lon": self.graph.stations[s_sid]["lon"],
                            "to_station": s_sid,
                        } if s_dist > 0 else None,
                        "end_walk": {
                            "distance_m": e_dist,
                            "duration_s": e_walk,
                            "from_lat": self.graph.stations[e_sid]["lat"],
                            "from_lon": self.graph.stations[e_sid]["lon"],
                            "to_lat": end_lat, "to_lon": end_lon,
                            "from_station": e_sid,
                        } if e_dist > 0 else None,
                    }

        return best_result

    def _dijkstra(self, start: str, end: str) -> dict[str, Any]:
        """Dijkstra on the routing graph from start station to end station.

        Returns: {cost, display, transfers, modes, steps, path, distance}
        - cost: routing cost (used by dijkstra to find shortest path)
        - display: user-facing time
        - transfers: count of line changes
        """
        dist: dict[str, float] = {start: 0.0}
        prev: dict[str, str | None] = {start: None}
        prev_line: dict[str, str | None] = {start: None}
        transfers: dict[str, int] = {start: 0}
        display: dict[str, float] = {start: 0.0}
        pq: list[tuple[float, str]] = [(0.0, start)]
        visited: set[str] = set()

        while pq:
            cost, cur = heapq.heappop(pq)
            if cur in visited:
                continue
            visited.add(cur)
            if cur == end:
                break
            for edge in self.graph.edges.get(cur, []):
                nb = edge["to"]
                if nb in visited:
                    continue
                base = edge["cost"]
                edge_type = edge["type"]
                eline = edge.get("line") if edge_type == "transit" else None
                extra = 0.0
                if edge_type == "transit":
                    in_line = prev_line.get(cur)
                    if in_line is not None and eline != in_line:
                        extra += TRANSFER_ROUTING_PENALTY_SEC
                new_cost = cost + base + extra
                new_display = display[cur] + edge["display_time"]
                if nb not in dist or new_cost < dist[nb]:
                    dist[nb] = new_cost
                    prev[nb] = cur
                    prev_line[nb] = eline if edge_type == "transit" else prev_line.get(cur)
                    transfers[nb] = transfers[cur] + (1 if extra > 0 else 0)
                    display[nb] = new_display
                    heapq.heappush(pq, (new_cost, nb))

        if end not in prev:
            return {"error": "No path"}

        # Reconstruct
        path, cur = [], end
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()

        # Build steps
        steps = []
        total_dist = 0.0
        cur_line = None
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            edge = next((e for e in self.graph.edges.get(a, [])
                        if e["to"] == b), None)
            if edge is None:
                continue
            sa = self.graph.stations[a]
            sb = self.graph.stations[b]
            is_transit = edge["type"] == "transit"
            is_xfer = (cur_line is not None
                      and edge.get("line") != cur_line)
            step = {
                "type": edge["type"],
                "from_station": a,
                "to_station": b,
                "from_lat": sa["lat"], "from_lon": sa["lon"],
                "to_lat": sb["lat"], "to_lon": sb["lon"],
                "distance_m": edge["distance"],
                "duration_s": edge["display_time"],
                "line": edge.get("line"),
                "is_transfer": is_xfer,
            }
            if is_transit:
                step["stop_name"] = sb["name"]
                cur_line = edge.get("line")
            else:
                step["stop_name"] = (
                    f"Walk {sa['name']} → {sb['name']}")
            steps.append(step)
            total_dist += edge["distance"]

        return {
            "cost": dist[end],
            "display": display[end],
            "transfers": transfers[end],
            "modes": self._merge_modes(steps),
            "steps": steps,
            "path": path,
            "distance": total_dist,
        }

    def _merge_modes(self, steps: list[dict]) -> list[str]:
        """Merge consecutive same-mode steps into mode segments."""
        if not steps:
            return []
        modes = []
        last = None
        for s in steps:
            if s["type"] != last:
                modes.append(s["type"])
                last = s["type"]
        return modes


def build_graph() -> tuple[RoutingGraph, Router]:
    """Load the seed file and build the full routing graph."""
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    print(f"Loading seed: {len(seed['stations'])} stations, "
          f"{len(seed['lines'])} lines")
    g = RoutingGraph(seed)
    nw = g.add_walk_edges()
    nt = sum(1 for edges in g.edges.values() for e in edges if e["type"] == "transit")
    print(f"Graph: {len(g.stations)} stations, {len(g.lines)} lines, "
          f"{nt} transit edges, {nw} walk edges")
    return g, Router(g)


if __name__ == "__main__":
    g, r = build_graph()
    print()

    # Quick sanity: Tborba → Cité Ennasr
    res = r.route(36.8151533, 10.0568158, 36.8585478, 10.1682756)
    print("=== Tborba → Cité Ennasr 1 (expected ~95 min via Metro 4 → Bus 5D) ===")
    print(f"  duration_min: {res['duration_min']}")
    print(f"  transfers: {res['transfers']}")
    print(f"  modes: {res['modes']}")
    print(f"  start_station: {res['start_station']}")
    print(f"  end_station: {res['end_station']}")
    if res["steps"]:
        print(f"  {len(res['steps'])} steps:")
        for s in res["steps"]:
            extra = f" [{s.get('line','')}]" if s.get("line") else ""
            xf = " TRANSFER" if s.get("is_transfer") else ""
            print(f"    {s['type']:8s} {s.get('duration_s',0):6.1f}s "
                  f"{s.get('distance_m',0):6.0f}m{extra}{xf} "
                  f"{str(s.get('stop_name',''))[:45]}")
