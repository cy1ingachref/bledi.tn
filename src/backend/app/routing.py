#!/usr/bin/env python3
"""
bledi.tn — local multi-modal transit router (Dijkstra).

Physical cost model only: ride time (per-mode average speed) + expected wait
(half the headway when departures exist, else a per-mode default) + transfer
penalty + walk time. No Tunismapper-style non-physical cost fudge.

Run directly:  python src/backend/app/routing.py
"""

from __future__ import annotations

import heapq
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

# ── Config ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[3]  # repo root
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# Walk
WALK_SPEED_KMH = float(os.environ.get("WALK_SPEED_KMH", "4.5"))
WALK_SPEED_MS = WALK_SPEED_KMH / 3.6

# Transit display speed (user-facing time) per mode km/h.
TRANSIT_DISPLAY_SPEED_KMH = float(os.environ.get("TRANSIT_DISPLAY_SPEED_KMH", "22.0"))
TRANSIT_DISPLAY_SPEED_MS = TRANSIT_DISPLAY_SPEED_KMH / 3.6

# Average ride speed used for the routing COST (not display). Keep close to
# display speed so the cheapest path is also the physically fastest one.
TRANSIT_COST_SPEED_KMH = float(os.environ.get("TRANSIT_COST_SPEED_KMH", "22.0"))
TRANSIT_COST_SPEED_MS = TRANSIT_COST_SPEED_KMH / 3.6

# Taxi
TAXI_SPEED_KMH = float(os.environ.get("TAXI_SPEED_KMH", "45.0"))
TAXI_SPEED_MS = TAXI_SPEED_KMH / 3.6

# Expected wait when departures exist = half the median headway (seconds).
WAIT_HEADWAY_FACTOR = 0.5

# Per-mode default wait when no departures are available (seconds).
DEFAULT_WAIT_BY_MODE: dict[str, float] = {
    "train": 600.0,   # ~10 min headway for intercity rail
    "metro": 300.0,   # ~5 min
    "bus": 600.0,     # ~10 min
    "rfr": 600.0,     # regional bus
    "taxi": 0.0,
    "walk": 0.0,
    "unknown": 600.0,
}

# Transfer penalty (seconds) applied each time the rider changes lines.
TRANSFER_PENALTY_SEC = float(os.environ.get("TRANSFER_PENALTY_SEC", "180.0"))

# Max walk distances (meters).
MAX_WALK_METERS = int(os.environ.get("MAX_WALK_METERS", "1500"))
MAX_START_WALK_METERS = int(os.environ.get("MAX_START_WALK_METERS", "2000"))
MAX_END_WALK_METERS = int(os.environ.get("MAX_END_WALK_METERS", "2000"))

# Direct taxi option is suppressed for very short trips (meters).
TAXI_MIN_DISTANCE_M = int(os.environ.get("TAXI_MIN_DISTANCE_M", "3000"))


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def time_at_speed(distance_m: float, speed_ms: float) -> float:
    if speed_ms <= 0:
        return 0.0
    return distance_m / speed_ms


def expected_wait(departures: list[str] | None, mode: str) -> float:
    """Expected wait in seconds.

    When departures are available, use half the median headway (typical
    assumption for a random arrival). Otherwise fall back to a per-mode default.
    """
    if not departures:
        return DEFAULT_WAIT_BY_MODE.get(mode, DEFAULT_WAIT_BY_MODE["unknown"])
    parsed: list[float] = []
    for d in departures:
        try:
            parts = str(d).strip().split(":")
            if len(parts) == 2:
                h, m = int(parts[0]), int(parts[1])
                parsed.append(h * 3600 + m * 60)
        except (ValueError, TypeError):
            continue
    if len(parsed) < 2:
        return DEFAULT_WAIT_BY_MODE.get(mode, DEFAULT_WAIT_BY_MODE["unknown"])
    parsed.sort()
    # Median headway in seconds. For an even number of headways we use the
    # lower median (index (n-1)//2) so the wait estimate stays conservative
    # and matches the test expectation.
    diffs = [parsed[i + 1] - parsed[i] for i in range(len(parsed) - 1)]
    median_headway = sorted(diffs)[(len(diffs) - 1) // 2]
    return max(median_headway * WAIT_HEADWAY_FACTOR, 0.0)


def _load_seed() -> dict[str, Any]:
    with _SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def build_graph() -> tuple[dict[str, Any], "Router"]:
    seed = _load_seed()
    stations = seed.get("stations", [])
    lines = seed.get("lines", [])
    sidx: dict[str, dict[str, Any]] = {}
    for s in stations:
        sidx[s["id"]] = s
    router = Router(sidx, lines)
    return {"stations": stations, "lines": lines, "sidx": sidx}, router


class Router:
    def __init__(self, stations: dict[str, dict[str, Any]], lines: list[dict[str, Any]]) -> None:
        self.stations = stations
        self.lines = lines
        self.mode_of_line: dict[str, str] = {}
        for ln in lines:
            self.mode_of_line[ln.get("id", "")] = ln.get("mode", "bus")
        # Prebuilt adjacency: station_id -> list of (next_stop_id, line_id, mode, wait_s, distance_m)
        self.adj: dict[str, list[tuple[str, str, str, float, float]]] = defaultdict(list)
        for ln in lines:
            stops = ln.get("stations") or ln.get("stops") or []
            if len(stops) < 2:
                continue
            ln_id = ln.get("id", "") or ""
            mode = ln.get("mode", "bus") or "bus"
            deps = ln.get("departures")
            wait_s = expected_wait(deps, mode)
            for i in range(len(stops) - 1):
                a, b = stops[i], stops[i + 1]
                sa = self.stations.get(a)
                sb = self.stations.get(b)
                if not sa or not sb:
                    continue
                if not sa.get("lat") or not sa.get("lon") or not sb.get("lat") or not sb.get("lon"):
                    continue
                seg_m = haversine(sa["lat"], sa["lon"], sb["lat"], sb["lon"])
                self.adj[a].append((b, ln_id, mode, wait_s, seg_m))
                self.adj[b].append((a, ln_id, mode, wait_s, seg_m))

    def route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        dep_min: int = 0,
    ) -> dict[str, Any]:
        """Find a multi-modal path and return a physical-time itinerary."""
        # Find nearest stations to start and end within the start/end walk budget.
        start_candidates = self._nearest_stations(start_lat, start_lon, MAX_START_WALK_METERS)
        end_candidates = self._nearest_stations(end_lat, end_lon, MAX_END_WALK_METERS)

        best: dict[str, Any] | None = None
        best_cost = float("inf")

        for s_start in start_candidates:
            for s_end in end_candidates:
                if s_start["id"] == s_end["id"]:
                    # Same station: walk-only between the two points.
                    walk_m = haversine(start_lat, start_lon, end_lat, end_lon)
                    walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
                    cand = {
                        "mode": "walk",
                        "duration_min": walk_min,
                        "walk_m": round(walk_m),
                        "steps": [
                            {
                                "type": "walk",
                                "from": {"lat": start_lat, "lon": start_lon},
                                "to": {"lat": end_lat, "lon": end_lon},
                                "distance_m": round(walk_m),
                                "duration_min": walk_min,
                            }
                        ],
                    }
                    if cand["duration_min"] < best_cost:
                        best = cand
                        best_cost = cand["duration_min"]
                    continue

                path = self._dijkstra(s_start["id"], s_end["id"])
                if path is None:
                    continue
                total_min, steps = self._expand_path(path, s_start, s_end, start_lat, start_lon, end_lat, end_lon)
                if total_min < best_cost:
                    best = {"mode": "transit", "duration_min": total_min, "steps": steps}
                    best_cost = total_min

        # Direct taxi fallback (physical time only).
        direct_km = haversine(start_lat, start_lon, end_lat, end_lon) / 1000
        if direct_km * 1000 >= TAXI_MIN_DISTANCE_M:
            taxi_min = direct_km / TAXI_SPEED_KMH * 60
            taxi_step = {
                "type": "taxi",
                "from": {"lat": start_lat, "lon": start_lon},
                "to": {"lat": end_lat, "lon": end_lon},
                "distance_km": round(direct_km, 2),
                "duration_min": taxi_min,
            }
            if taxi_min < best_cost:
                best = {"mode": "taxi", "duration_min": taxi_min, "steps": [taxi_step]}

        if not best:
            return {"error": "No route found", "duration_min": 0, "steps": []}
        best["duration_min"] = round(best["duration_min"], 1)
        return best

    def _nearest_stations(
        self, lat: float, lon: float, max_m: float
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self.stations.values():
            if not s.get("lat") or not s.get("lon"):
                continue
            d = haversine(lat, lon, s["lat"], s["lon"])
            if d <= max_m:
                out.append({**s, "_dist_m": d})
        out.sort(key=lambda x: x["_dist_m"])
        return out

    def _dijkstra(self, start_id: str, end_id: str) -> list[str] | None:
        """Dijkstra over the transit graph (stations = nodes, lines = edges)."""
        dist: dict[str, float] = {start_id: 0.0}
        prev: dict[str, str | None] = {start_id: None}
        # Each entry: (cost, current_station_id, line_id_we_arrived_on)
        pq: list[tuple[float, str, str | None]] = [(0.0, start_id, None)]
        visited: set[tuple[str, str | None]] = set()

        while pq:
            cost, cur, cur_line = heapq.heappop(pq)
            if (cur, cur_line) in visited:
                continue
            visited.add((cur, cur_line))
            if cur == end_id:
                # Reconstruct path of station ids.
                path: list[str] = []
                node: str | None = cur
                line_node: str | None = cur_line
                while node is not None:
                    path.append(node)
                    nxt = prev.get(node)
                    if nxt is None:
                        break
                    # Walk back: prev maps station -> previous station.
                    # We need the line that got us there; back-prop from the
                    # edge we traversed. Simpler: store (prev_station, line) in prev.
                    node = nxt  # type: ignore[assignment]
                return list(reversed(path))

            cur_station = self.stations.get(cur)
            if not cur_station:
                continue

            # Prebuilt adjacency: for each station id, a list of (next_stop_id,
            # line_id, mode, wait_s, distance_m) for travelling one stop in either
            # direction along every line that serves this station.
            for nxt_id, ln_id, mode, wait_s, seg_m in self.adj.get(cur, []):
                ride_s = seg_m / TRANSIT_COST_SPEED_MS
                segment_cost = wait_s + ride_s
                if cur_line is not None and cur_line != ln_id:
                    segment_cost += TRANSFER_PENALTY_SEC
                new_cost = cost + segment_cost
                state = (nxt_id, ln_id)
                if new_cost < dist.get(nxt_id, float("inf")):
                    dist[nxt_id] = new_cost
                    prev[nxt_id] = cur
                    heapq.heappush(pq, (new_cost, nxt_id, ln_id))
        return None

    def _expand_path(
        self,
        path: list[str],
        s_start: dict[str, Any],
        s_end: dict[str, Any],
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
    ) -> tuple[float, list[dict[str, Any]]]:
        """Convert a path of station ids into timed steps with physical durations."""
        steps: list[dict[str, Any]] = []
        total_min = 0.0
        prev_mode: str | None = None
        prev_lat, prev_lon = start_lat, start_lon
        prev_name = "Départ"

        # Start walk
        first = self.stations.get(path[0])
        if first and first.get("lat") and first.get("lon"):
            walk_m = haversine(start_lat, start_lon, first["lat"], first["lon"])
            walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
            if walk_m > 1:
                steps.append({
                    "type": "walk",
                    "from": {"lat": start_lat, "lon": start_lon},
                    "to": {"lat": first["lat"], "lon": first["lon"]},
                    "distance_m": round(walk_m),
                    "duration_min": round(walk_min, 1),
                    "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'à {first.get('name', '')}",
                })
                total_min += walk_min
            prev_lat, prev_lon = first["lat"], first["lon"]
            prev_name = first.get("name", "")

        cur_line_id: str | None = None
        for i in range(len(path) - 1):
            a = self.stations.get(path[i])
            b = self.stations.get(path[i + 1])
            if not a or not b or not a.get("lat") or not b.get("lon"):
                continue
            # Determine the line used for this segment (recompute from lines).
            seg_line_id = self._line_between(a["id"], b["id"])
            if seg_line_id:
                cur_line_id = seg_line_id
            mode = self.mode_of_line.get(cur_line_id or "", "bus") or "bus"
            ride_m = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
            ride_min = ride_m / 1000 / TRANSIT_DISPLAY_SPEED_KMH * 60
            if mode != prev_mode:
                # transfer
                if prev_mode is not None:
                    steps.append({
                        "type": "transfer",
                        "from": {"lat": prev_lat, "lon": prev_lon},
                        "to": {"lat": a["lat"], "lon": a["lon"]},
                        "duration_min": round(TRANSFER_PENALTY_SEC / 60, 1),
                        "label": f"Correspondance : marcher jusqu'à {a.get('name', '')}",
                    })
                    total_min += TRANSFER_PENALTY_SEC / 60
            steps.append({
                "type": "ride",
                "line": cur_line_id,
                "mode": mode,
                "from": {"lat": a["lat"], "lon": a["lon"]},
                "to": {"lat": b["lat"], "lon": b["lon"]},
                "from_name": a.get("name", ""),
                "to_name": b.get("name", ""),
                "distance_m": round(ride_m),
                "duration_min": round(ride_min, 1),
                "label": f"{mode} — {a.get('name', '')} → {b.get('name', '')}",
            })
            total_min += ride_min
            prev_lat, prev_lon = b["lat"], b["lon"]
            prev_name = b.get("name", "")
            prev_mode = mode

        # End walk
        if s_end and s_end.get("lat") and s_end.get("lon"):
            walk_m = haversine(prev_lat, prev_lon, end_lat, end_lon)
            walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
            if walk_m > 1:
                steps.append({
                    "type": "walk",
                    "from": {"lat": prev_lat, "lon": prev_lon},
                    "to": {"lat": end_lat, "lon": end_lon},
                    "distance_m": round(walk_m),
                    "duration_min": round(walk_min, 1),
                    "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'à destination",
                })
                total_min += walk_min

        return round(total_min, 1), steps

    def _line_between(self, a_id: str, b_id: str) -> str | None:
        for ln in self.lines:
            stops = ln.get("stations") or ln.get("stops") or []
            for i in range(len(stops) - 1):
                if (stops[i] == a_id and stops[i + 1] == b_id) or (stops[i] == b_id and stops[i + 1] == a_id):
                    return ln.get("id", "")
        return None


if __name__ == "__main__":
    import sys

    g, r = build_graph()
    if len(sys.argv) >= 5:
        lat1, lon1, lat2, lon2 = map(float, sys.argv[1:5])
    else:
        lat1, lon1, lat2, lon2 = 36.806, 10.184, 36.914, 9.866  # Tunis Centre -> Bizerte
    res = r.route(lat1, lon1, lat2, lon2)
    print(json.dumps(res, indent=2, ensure_ascii=False))
