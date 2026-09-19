#!/usr/bin/env python3
"""Multi-modal routing engine for bledi.tn.

Takes a start point (lat/lng) and end point (lat/lng), finds the nearest
stations, builds a graph of connected stations, and computes the optimal
route using Dijkstra's algorithm. Supports:
  - Walking (to/from stations)
  - Transit (bus/metro/train along route lines)
  - Taxi (direct point-to-point)

Output: JSON with route legs, total duration, distance, transfers.
"""
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path

BASE = Path("C:/Users/cy1in/Downloads/TunisiaTransport")

# Speed constants (km/h)
WALK_SPEED = 5.0
TAXI_SPEED = 40.0
TRANSIT_SPEED = 25.0  # average including stops
TRANSFER_PENALTY = 5.0  # minutes penalty per transfer


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two points."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def walk_time(dist_km):
    """Walking time in minutes."""
    return (dist_km / WALK_SPEED) * 60


def taxi_time(dist_km):
    """Taxi time in minutes."""
    return (dist_km / TAXI_SPEED) * 60


def transit_time(dist_km):
    """Transit time in minutes (including stops)."""
    return (dist_km / TRANSIT_SPEED) * 60


class RoutingEngine:
    """Multi-modal routing engine using station graph."""

    def __init__(self, seed_path):
        with open(seed_path, encoding="utf-8") as f:
            self.seed = json.load(f)
        self.stations = {s["id"]: s for s in self.seed["stations"]}
        self.lines = self.seed["lines"]
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build adjacency graph: station_id -> [(neighbor_id, line_id, mode)]."""
        graph = defaultdict(list)
        for line in self.lines:
            station_ids = line.get("stations", [])
            for i in range(len(station_ids) - 1):
                sid1 = station_ids[i]
                sid2 = station_ids[i + 1]
                if sid1 in self.stations and sid2 in self.stations:
                    graph[sid1].append((sid2, line["id"], line["mode"]))
                    graph[sid2].append((sid1, line["id"], line["mode"]))
        return graph

    def nearest_station(self, lat, lon, max_dist_km=5.0):
        """Find the nearest station to a point."""
        best = None
        best_dist = float("inf")
        for sid, station in self.stations.items():
            if station.get("lat") and station.get("lon"):
                dist = haversine(lat, lon, station["lat"], station["lon"])
                if dist < best_dist and dist <= max_dist_km:
                    best_dist = dist
                    best = sid
        return best, best_dist

    def find_route(self, start_lat, start_lon, end_lat, end_lon):
        """Find multi-modal route from start to end.

        Returns dict with:
          - legs: list of route segments
          - total_duration: minutes
          - total_distance: km
          - transfers: number
        """
        # Find nearest stations
        start_sid, start_dist = self.nearest_station(start_lat, start_lon)
        end_sid, end_dist = self.nearest_station(end_lat, end_lon)

        if not start_sid or not end_sid:
            return {"error": "No nearby stations found"}

        # Check if same station
        if start_sid == end_sid:
            return {
                "legs": [{
                    "type": "walk",
                    "from": (start_lat, start_lon),
                    "to": (end_lat, end_lon),
                    "distance": haversine(start_lat, start_lon, end_lat, end_lon),
                    "duration": walk_time(haversine(start_lat, start_lon, end_lat, end_lon)),
                }],
                "total_duration": walk_time(haversine(start_lat, start_lon, end_lat, end_lon)),
                "total_distance": haversine(start_lat, start_lon, end_lat, end_lon),
                "transfers": 0,
            }

        # Dijkstra's algorithm
        # State: (station_id, current_line_id) -> best_duration
        # We track line_id to apply transfer penalties
        dist = {}
        prev = {}
        pq = []

        # Initialize: walk to start station
        start_walk_time = walk_time(start_dist)
        dist[(start_sid, None)] = start_walk_time
        heapq.heappush(pq, (start_walk_time, start_sid, None))

        found = None

        while pq:
            d, sid, line_id = heapq.heappop(pq)

            if sid == end_sid:
                found = (d, sid, line_id)
                break

            if d > dist.get((sid, line_id), float("inf")):
                continue

            # Explore neighbors
            for neighbor, edge_line_id, mode in self.graph.get(sid, []):
                # Calculate edge weight
                s1 = self.stations[sid]
                s2 = self.stations[neighbor]
                edge_dist = haversine(s1["lat"], s1["lon"], s2["lat"], s2["lon"])

                if mode == "bus":
                    edge_time = transit_time(edge_dist)
                elif mode == "metro":
                    edge_time = transit_time(edge_dist) * 0.8  # faster
                elif mode == "train":
                    edge_time = transit_time(edge_dist) * 1.2  # slower (stops)
                else:
                    edge_time = transit_time(edge_dist)

                # Transfer penalty
                transfer_penalty = TRANSFER_PENALTY if line_id and line_id != edge_line_id else 0

                new_dist = d + edge_time + transfer_penalty

                if new_dist < dist.get((neighbor, edge_line_id), float("inf")):
                    dist[(neighbor, edge_line_id)] = new_dist
                    prev[(neighbor, edge_line_id)] = (sid, line_id)
                    heapq.heappush(pq, (new_dist, neighbor, edge_line_id))

        if not found:
            return {"error": "No route found"}

        # Reconstruct path
        path = []
        cur = (found[1], found[2])
        while cur in prev:
            path.append(cur)
            cur = prev[cur]
        path.append((start_sid, None))
        path.reverse()

        # Build legs
        legs = []
        total_transit_dist = 0

        # Walk to start station
        if start_dist > 0:
            legs.append({
                "type": "walk",
                "from": (start_lat, start_lon),
                "to": (self.stations[start_sid]["lat"], self.stations[start_sid]["lon"]),
                "distance": start_dist,
                "duration": start_walk_time,
                "station": self.stations[start_sid]["name"],
            })

        # Transit legs
        transfers = 0
        for i in range(len(path) - 1):
            sid1, line_id1 = path[i]
            sid2, line_id2 = path[i + 1]

            s1 = self.stations[sid1]
            s2 = self.stations[sid2]
            edge_dist = haversine(s1["lat"], s1["lon"], s2["lat"], s2["lon"])
            total_transit_dist += edge_dist

            # Find line info
            line_info = next((l for l in self.lines if l["id"] == line_id2), None)
            mode = line_info["mode"] if line_info else "bus"

            legs.append({
                "type": "transit",
                "mode": mode,
                "line": line_info["number"] if line_info else "?",
                "from_station": s1["name"],
                "to_station": s2["name"],
                "distance": edge_dist,
                "duration": transit_time(edge_dist),
            })

            if line_id1 and line_id1 != line_id2:
                transfers += 1

        # Walk from end station
        if end_dist > 0:
            legs.append({
                "type": "walk",
                "from": (self.stations[end_sid]["lat"], self.stations[end_sid]["lon"]),
                "to": (end_lat, end_lon),
                "distance": end_dist,
                "duration": walk_time(end_dist),
                "station": self.stations[end_sid]["name"],
            })

        total_duration = sum(leg["duration"] for leg in legs)
        total_distance = sum(leg["distance"] for leg in legs)

        return {
            "legs": legs,
            "total_duration": round(total_duration, 1),
            "total_distance": round(total_distance, 2),
            "transfers": transfers,
            "start_station": self.stations[start_sid]["name"],
            "end_station": self.stations[end_sid]["name"],
        }


def main():
    engine = RoutingEngine(BASE / "data/seed_all_tunisia_routes.json")

    # Test: Tborba to Cite Ennasr 1 (same as Tunismapper example)
    result = engine.find_route(
        start_lat=36.8151533, start_lon=10.0568158,
        end_lat=36.8585478, end_lon=10.1682756,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
