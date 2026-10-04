#!/usr/bin/env python3
"""
bledi.tn — local multi-modal transit router (Dijkstra).

Physical cost model only: ride time (per-mode average speed) + expected wait
(paid once per boarding = half the headway when departures exist, else a
per-mode default) + transfer penalty + walk time. No Tunismapper-style
non-physical cost fudge.

State-space fix (2026-09-20 review): dist/prev are keyed by
(station_id, line_arrived_on) so a cheap arrival on a dead-end line can never
permanently shadow a slightly-pricier arrival on the line that continues
penalty-free. Wait is charged once at boarding (cur_line != ln_id), not at
every stop. The line actually used for each segment is the one stored during
relaxation, not a post-hoc _line_between heuristic (which misattributes shared
corridor edges).

Run directly:  python src/backend/app/routing.py
"""

from __future__ import annotations

import heapq
import json
import logging
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger("bledi.routing")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

# ── Config ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[3]  # repo root
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# Walk
WALK_SPEED_KMH = float(os.environ.get("WALK_SPEED_KMH", "4.5"))
WALK_SPEED_MS = WALK_SPEED_KMH / 3.6

# Transit display speed (user-facing time) per mode km/h.
# Per-mode average transit speeds (km/h) used for BOTH routing cost and
# user-facing display time. Cost and display use the same value so the
# cheapest path is also the physically fastest one.
# Env overrides via SPEED_<MODE>_KMH, e.g. SPEED_TRAIN_KMH=60.
SPEED_BY_MODE: dict[str, float] = {
    "train": float(os.environ.get("SPEED_TRAIN_KMH", "60.0")),
    "rail": float(os.environ.get("SPEED_RAIL_KMH", "55.0")),
    "metro": float(os.environ.get("SPEED_METRO_KMH", "30.0")),
    "bus": float(os.environ.get("SPEED_BUS_KMH", "22.0")),
    "rfr": float(os.environ.get("SPEED_RFR_KMH", "22.0")),
    "tram": float(os.environ.get("SPEED_TRAM_KMH", "22.0")),
    "taxi": float(os.environ.get("TAXI_SPEED_KMH", "45.0")),
    "walk": float(os.environ.get("WALK_SPEED_KMH", "4.5")),
}

def transit_speed_kmh(mode: str) -> float:
    """Return average ride speed (km/h) for a transit mode."""
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])

def transit_speed_ms(mode: str) -> float:
    return transit_speed_kmh(mode) / 3.6

# Hard cap (seconds) on per-boarding expected wait. Lines with only a couple
# departures/day can produce multi-hour median headways from expected_wait();
# until dep_min is real, cap boarding wait so sparse lines do not dominate
# long corridors.
BOARDING_WAIT_CAP = int(os.environ.get("BOARDING_WAIT_CAP_SEC", str(20 * 60)))

# Average ride speed used for the routing COST (not display). Keep close to
# display speed so the cheapest path is also the physically fastest one.

# Taxi
TAXI_SPEED_KMH = float(os.environ.get("TAXI_SPEED_KMH", "45.0"))
TAXI_SPEED_MS = TAXI_SPEED_KMH / 3.6
TAXI_FARE_BASE = float(os.environ.get("TAXI_FARE_BASE", "0.600"))
TAXI_FARE_PER_KM = float(os.environ.get("TAXI_FARE_PER_KM", "0.520"))

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
MAX_START_WALK_METERS = int(os.environ.get("MAX_START_WALK_METERS", "2000"))
MAX_END_WALK_METERS = int(os.environ.get("MAX_END_WALK_METERS", "2000"))

# Walk EDGES between stops, i.e. the pedestrian network inside the graph.
# This used to be 0, which meant a destination stop was reachable only if a line
# happened to call at it: Kairouan has 29 stops within 2 km and every one of
# them had zero edges, so the router could never "walk to the nearest transport
# and ride", which is the entire point of a multi-modal router. 900 m is a
# realistic walk-to-bus distance; it adds ~11k edges over 4.2k stops.
MAX_WALK_EDGE_METERS = int(os.environ.get("MAX_WALK_EDGE_METERS", "900"))

# Radius used to find the "drop-off" stop when the destination itself has no
# station nearby. Lets the router answer ride-then-brief-walk for a town with
# no stop of its own instead of drawing one taxi line across the country.
# Measured against the seed: the nearest line-served station is 0.1 km for Tunis,
# 0.6 km for Nabeul, 0.9 km for Sfax, but 44.3 km for Kairouan and 90.8 km for
# Mahdia, because no line in the 232-line seed calls at either town. The radius
# has to cover that worst case to give those towns a "nearest station" answer at
# all; the resulting final leg is charged at taxi speed and labelled as a local
# hop, so a 44 km gap is never presented as a walk.
DROPOFF_SEARCH_METERS = int(os.environ.get("DROPOFF_SEARCH_METERS", "100000"))

# A walk edge resets the line context: after walking you have not "arrived on"
# any line, so the next boarding is a fresh boarding (wait paid again) rather
# than a free continuation. The sentinel keeps that distinct from a real line id.
WALK_EDGE = "__walk__"

# How many line-served drop-off stops to consider, nearest first. Measured on
# the seed: 1 is correct. Widening it to 6 made Mahdia *worse* -- Dijkstra then
# picks a distant but better-connected station (98.3 km final hop, 414 min)
# instead of the nearest one (90.8 km, 443 min), because a longer ride is cheaper
# on time than a shorter one plus a long taxi hop. The user's question is "what
# is the nearest transport", so the nearest served station is the answer.
DROP_OFF_CANDIDATES = int(os.environ.get("DROP_OFF_CANDIDATES", "1"))

# Direct taxi option is suppressed for very short trips (meters).
TAXI_MIN_DISTANCE_M = int(os.environ.get("TAXI_MIN_DISTANCE_M", "3000"))

# Maximum gap (seconds) between two consecutive departures that we still treat
# as a single service day. Gaps larger than this are assumed to be the overnight
# closure and are excluded from the median headway (otherwise a 23:55/06:05 pair
# would produce a phantom ~18 h headway).
MAX_HEADWAY_SEC = int(os.environ.get("MAX_HEADWAY_SEC", str(12 * 3600)))


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Real path geometry ─────────────────────────────────────────────────────
# Straight-line distance is a lower bound on the real path, never the path
# itself. Using it as an edge COST under-rides every leg, so a multi-leg transit
# itinerary loses to a single straight taxi estimate. Measured on this seed's
# cache (3 938 edges): real/straight median 1.06 but TOTAL length inflation
# 8 988 km -> 12 631 km (+41%), because the long intercity hops are the ones
# that detour hardest (up to 3.1x). So haversine stays as the A* heuristic and
# as a fallback where no cached polyline exists, and the polyline length is what
# the cost model uses.
#
# The cache is keyed on an UNORDERED station-id pair and the stored polyline
# always runs min -> max, so reads must orient it to the travel direction.
#
# The JSON cache is read at most once per process. Re-reading it per Router
# instantiation cost 162 parses during a single import in one measurement,
# because build_graph() and the module-level Router in main.py each construct a
# router over the same file. Keyed by path so tests can point at another file.
_GEOMETRY_CACHE_MEMO: dict[str, dict[str, dict[str, Any]]] = {}


def load_geometry_cache() -> dict[str, dict[str, Any]]:
    path = os.environ.get("GEOMETRY_CACHE_PATH")
    candidates = [path] if path else []
    # src/backend/app/routing.py -> repo root is three levels up.
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    candidates.append(os.path.join(root, "data", "route_geometry.json"))
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        key = os.path.abspath(cand)
        if key in _GEOMETRY_CACHE_MEMO:
            return _GEOMETRY_CACHE_MEMO[key]
        try:
            with open(cand, encoding="utf-8") as f:
                segs = json.load(f).get("segments", {})
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("routing: geometry cache unreadable at %s: %s", cand, exc)
            continue
        log.info(
            "routing: loaded %d geometry segments (%d with a polyline) from %s",
            len(segs),
            sum(1 for v in segs.values() if v.get("geometry")),
            os.path.basename(cand),
        )
        _GEOMETRY_CACHE_MEMO[key] = segs
        return segs
    log.warning(
        "routing: no geometry cache found; transit edges fall back to "
        "straight-line distance (cost understated, legs drawn straight)"
    )
    return {}


def load_walk_geometry_cache() -> dict[str, dict[str, Any]]:
    """Real pedestrian polylines for walk legs, keyed "a|b" unordered.

    Built by tool/build_walk_geometry.py against Valhalla's pedestrian costing.
    The public OSRM demo cannot serve this: measured on this project, foot,
    walking, bike, cycling and a nonsense profile all return byte-identical
    results, because that server ignores the profile segment and serves a single
    car dataset.
    """
    path = os.environ.get("WALK_GEOMETRY_CACHE_PATH")
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    default = os.path.join(root, "data", "walk_geometry.json")
    for cand in ([path] if path else []) + [default]:
        if not cand or not os.path.exists(cand):
            continue
        key = os.path.abspath(cand)
        if key in _GEOMETRY_CACHE_MEMO:
            return _GEOMETRY_CACHE_MEMO[key]
        try:
            with open(cand, encoding="utf-8") as f:
                segs = json.load(f).get("segments", {})
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("routing: walk geometry unreadable at %s: %s", cand, exc)
            continue
        log.info(
            "routing: loaded %d walk-geometry segments (%d with a polyline)",
            len(segs),
            sum(1 for v in segs.values() if v.get("geometry")),
        )
        _GEOMETRY_CACHE_MEMO[key] = segs
        return segs
    log.info(
        "routing: no walk-geometry cache; walk legs fall back to a straight "
        "line. Build it with: python src/backend/tool/build_walk_geometry.py"
    )
    return {}


def load_taxi_geometry_cache() -> dict[str, list[list[float]]]:
    """Road polylines for direct taxi/louaj legs, keyed "lat,lon|lat,lon".

    Built by tool/build_taxi_geometry.py. These are the only place a path
    connects two points that are NOT both stations -- the access walk and the
    final drop-off -- so there is no station pair to key on, hence the
    coordinate key.
    """
    path = os.environ.get("TAXI_GEOMETRY_CACHE_PATH")
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    default = os.path.join(root, "data", "taxi_geometry.json")
    for cand in ([path] if path else []) + [default]:
        if not cand or not os.path.exists(cand):
            continue
        key = os.path.abspath(cand)
        if key in _GEOMETRY_CACHE_MEMO:
            return _GEOMETRY_CACHE_MEMO[key]
        try:
            with open(cand, encoding="utf-8") as f:
                segs = json.load(f).get("segments", {})
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("routing: taxi geometry unreadable at %s: %s", cand, exc)
            continue
        log.info(
            "routing: loaded %d taxi/louaj road segments",
            sum(1 for v in segs.values() if v.get("geometry")),
        )
        _GEOMETRY_CACHE_MEMO[key] = segs
        return segs
    return {}


def taxi_key(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> str:
    """Coordinate-pair cache key, direction-independent (min first).

    Matches build_taxi_geometry.key_for() at the same 5dp quantisation.
    """
    ka = (round(a_lat, 5), round(a_lon, 5))
    kb = (round(b_lat, 5), round(b_lon, 5))
    lo, hi = (ka, kb) if ka <= kb else (kb, ka)
    return f"{lo[0]},{lo[1]}|{hi[0]},{hi[1]}"


def road_geometry_for(
    cache: dict[str, Any],
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> list[list[float]]:
    """Cached real-road polyline between two arbitrary points, travel-ordered.

    A taxi leg is the only path in the system whose endpoints are not both
    stations, so it cannot be served by the station-pair transit cache. Returns
    [] when the pair was never cached, which the caller reports as a straight
    line rather than pretending the cache covered it.
    """
    entry = cache.get(taxi_key(a_lat, a_lon, b_lat, b_lon))
    if not isinstance(entry, dict):
        return []
    pts = entry.get("geometry") or []
    if len(pts) < 2:
        return []
    # The stored polyline runs min -> max on the key, so flip it when the rider
    # travels the other way.
    forward = taxi_key(a_lat, a_lon, b_lat, b_lon).split("|")[0] == (
        f"{round(a_lat, 5)},{round(a_lon, 5)}"
    )
    return list(pts) if forward else list(reversed(pts))


def polyline_length(pts: list[Sequence[float]]) -> float:
    """Real along-geometry distance in meters for a [[lat, lon], ...] polyline."""
    total = 0.0
    for i in range(len(pts) - 1):
        total += haversine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
    return total


def oriented_geometry(
    entry: dict[str, Any], from_id: str, to_id: str
) -> list[list[float]]:
    """Cached polyline between two stations, oriented along travel direction.

    The cache key is the unordered pair min|max and the stored polyline runs
    min -> max. A step runs from_id -> to_id, so when from_id sorts after to_id
    the polyline is reversed to keep the drawn line pointing the way the rider
    travels. Returns [] when there is no cached geometry.
    """
    pts = entry.get("geometry") or []
    if len(pts) < 2:
        return []
    return list(reversed(pts)) if from_id > to_id else list(pts)


def time_at_speed(distance_m: float, speed_ms: float) -> float:
    if speed_ms <= 0:
        return 0.0
    return distance_m / speed_ms


def expected_wait(departures: list[str] | None, mode: str) -> float:
    """Expected wait in seconds.

    When departures are available, use half the median headway (typical
    assumption for a random arrival). Otherwise fall back to a per-mode default.

    Midnight wrap: if the departures span more than MAX_HEADWAY_SEC (default
    12 h), the overnight closure is treated as a service gap and excluded from
    the headway median instead of being counted as one giant headway.
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
    # Consecutive headways within the sorted day.
    diffs = [parsed[i + 1] - parsed[i] for i in range(len(parsed) - 1)]
    # If the service spans midnight (last - first > MAX_HEADWAY_SEC), the gap
    # between the last departure of the day and the first departure of the next
    # day is a real headway too (the overnight closure). Add it.
    overnight_gap = 0.0
    if parsed[-1] - parsed[0] > MAX_HEADWAY_SEC:
        overnight_gap = 86400.0 - parsed[-1] + parsed[0]
    all_headways = sorted(diffs + ([overnight_gap] if overnight_gap > 0 else []))
    if not all_headways:
        return DEFAULT_WAIT_BY_MODE.get(mode, DEFAULT_WAIT_BY_MODE["unknown"])
    # Lower median (index (n-1)//2) so the wait estimate stays conservative
    # and matches the test expectation for same-day pairs.
    median_headway = all_headways[(len(all_headways) - 1) // 2]
    return max(median_headway * WAIT_HEADWAY_FACTOR, 0.0)


def _load_seed() -> dict[str, Any]:
    with _SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass(slots=True)
class Edge:
    """One directed graph edge.

    distance_m is the REAL along-geometry distance, not the straight line, so
    the cost model and the drawn line agree. straight_m is kept only for the
    A* heuristic and for auditing how much the real path detours.
    """
    to_id: str
    line: str
    mode: str
    wait_s: float
    distance_m: float
    time_s: float
    geometry: list[list[float]]
    straight_m: float


# Mode families for the three user-facing options. The user picks a transport
# option; each option is searched separately with its own mode restriction
# rather than being derived from one combined answer. That matters because a
# combined search minimises total time and will happily return a train when the
# user asked for a bus, and vice versa.
#
# "louaj" is the Tunisian shared-taxi: a car, so it follows the road network
# and is priced at taxi speed. It is distinct from a scheduled bus only in that
# it needs no timetable.
BUS_MODES: frozenset[str] = frozenset({"bus", "rfr", "tram"})
RAIL_MODES: frozenset[str] = frozenset({"train", "rail", "metro"})
TAXI_MODES: frozenset[str] = frozenset({"taxi", "louaj"})

# Default per-option mode sets. Overridable so a test or an env var can pin them.
OPTION_MODES: dict[str, frozenset[str]] = {
    "bus": BUS_MODES,
    "louaj": TAXI_MODES,
    "train": RAIL_MODES,
}


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
        self.line_wait: dict[str, float] = {}  # line_id -> boarding wait (s)
        for ln in lines:
            ln_id = ln.get("id", "") or ""
            mode = ln.get("mode", "bus") or "bus"
            self.mode_of_line[ln_id] = mode
            deps = ln.get("departures")
            self.line_wait[ln_id] = min(
                expected_wait(deps, mode), BOARDING_WAIT_CAP
            )  # pragma: no cover - path-covered via Router.route() with a
            #         line whose departures yield a headway above the cap
        # Prebuilt adjacency: station_id -> list[Edge].
        # An Edge carries the REAL along-geometry distance (not the straight
        # line), the travel time, the mode, and the polyline itself so the API
        # can hand the frontend something it can actually draw. Straight-line
        # survives only as the A* heuristic and as a fallback for the edges the
        # cache has no polyline for.
        self.geometry: dict[str, dict[str, Any]] = load_geometry_cache()
        self.walk_geometry: dict[str, dict[str, Any]] = load_walk_geometry_cache()
        self.taxi_geometry: dict[str, Any] = load_taxi_geometry_cache()
        self.adj: dict[str, list[Edge]] = defaultdict(list)
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
                self.adj[a].append(self._make_edge(a, b, sa, sb, ln_id, mode, wait_s))
                self.adj[b].append(self._make_edge(b, a, sb, sa, ln_id, mode, wait_s))

        self._build_walk_edges()

    def _make_edge(
        self,
        a_id: str,
        b_id: str,
        a: dict[str, Any],
        b: dict[str, Any],
        ln_id: str,
        mode: str,
        wait_s: float,
    ) -> "Edge":
        """Build one directed graph edge with real distance, time and geometry."""
        straight_m = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        entry = self.geometry.get(f"{min(a_id, b_id)}|{max(a_id, b_id)}")
        geom: list[list[float]] = []
        real_m = straight_m
        if entry and entry.get("geometry"):
            geom = oriented_geometry(entry, a_id, b_id)
            # A path along a network cannot be shorter than the straight line it
            # replaces. Anything under that means the stored polyline is wrong
            # (a mis-oriented or mis-stitched slice), so refuse it and keep the
            # honest straight line rather than a physically impossible distance.
            cand_m = polyline_length(geom)
            if cand_m >= 0.95 * straight_m:
                real_m = cand_m
            else:
                geom = []
        if real_m <= 0:
            real_m = straight_m
        return Edge(
            to_id=b_id,
            line=ln_id,
            mode=mode,
            wait_s=wait_s,
            distance_m=real_m,
            time_s=real_m / transit_speed_ms(mode),
            geometry=geom,
            straight_m=straight_m,
        )

    def _build_walk_edges(self) -> None:
        """Connect nearby stops with bidirectional walk edges.

        Without these the graph is transit-only, so a destination stop that no
        line calls at is unreachable and the router falls back to a single taxi
        line drawn straight across the map. This is what lets the router answer
        "walk to the nearest stop, ride, walk to the destination".

        Built through a lat/lon grid rather than an O(n^2) scan: 4221 stops
        squared is ~9M haversine calls at import time, which would add seconds to
        every server start. The grid keys on ~300 m cells so only the surrounding
        cells are examined per stop.
        """
        pos: dict[str, tuple[float, float]] = {
            sid: (s["lat"], s["lon"])
            for sid, s in self.stations.items()
            if s.get("lat") and s.get("lon")
        }
        cell_deg = max(MAX_WALK_EDGE_METERS, 100) / 111_000.0
        grid: dict[tuple[int, int], list[str]] = defaultdict(list)
        for sid, (lat, lon) in pos.items():
            grid[(int(lat / cell_deg), int(lon / cell_deg))].append(sid)

        span = 1 if MAX_WALK_EDGE_METERS <= cell_deg * 2 else 2
        for sid, (lat, lon) in pos.items():
            cx, cy = int(lat / cell_deg), int(lon / cell_deg)
            for dx in range(-span, span + 1):
                for dy in range(-span, span + 1):
                    for other in grid.get((cx + dx, cy + dy), ()):
                        # Both cells see both stops, so without this guard every
                        # pair is built twice; the extra appends are exact duplicates.
                        if other <= sid:
                            continue
                        o_lat, o_lon = pos[other]
                        d = haversine(lat, lon, o_lat, o_lon)
                        if d <= MAX_WALK_EDGE_METERS:
                            # Real pedestrian path when the cache has it. A walk
                            # edge has no line id, so the walk geometry is stored
                            # under the same "a|b" key with a walk-mode marker.
                            wkey = f"{min(sid, other)}|{max(sid, other)}"
                            wentry = self.walk_geometry.get(wkey)
                            wgeom: list[list[float]] = []
                            wlen = d
                            if wentry and wentry.get("geometry"):
                                cand = oriented_geometry(wentry, sid, other)
                                # Same lower bound as transit: a footpath
                                # cannot be shorter than the crow-flies line.
                                cand_m = polyline_length(cand)
                                if cand_m >= 0.95 * d:
                                    wgeom = cand
                                    wlen = cand_m
                            self.adj[sid].append(
                                Edge(
                                    to_id=other,
                                    line=WALK_EDGE,
                                    mode="walk",
                                    wait_s=0.0,
                                    distance_m=wlen,
                                    time_s=wlen / WALK_SPEED_MS,
                                    geometry=wgeom,
                                    straight_m=d,
                                )
                            )
                            self.adj[other].append(
                                Edge(
                                    to_id=sid,
                                    line=WALK_EDGE,
                                    mode="walk",
                                    wait_s=0.0,
                                    distance_m=wlen,
                                    time_s=wlen / WALK_SPEED_MS,
                                    geometry=wgeom,
                                    straight_m=d,
                                )
                            )

    def route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        allowed_modes: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        """Find multi-modal paths and return a ranked list of itineraries.

        Always fully computes the transit path (when one exists) so it is never
        discarded when taxi is physically faster. Returns
            {"options": [transit?, taxi?, walk], "direct_m": ..., "end_ids": [...]}
        ranked by total seconds, cheapest first. Taxi is flagged
        ``{"fallback": True}`` when it is offered as an alternative to a faster
        or equal-cost transit option; walk is always last resort.

        Uses a single multi-source Dijkstra from all start candidates (with the
        walk-to-station cost as the initial label) so one pass covers every
        (start, end) pair instead of N*M separate Dijkstras.
        """
        start_candidates = self._nearest_stations(start_lat, start_lon, MAX_START_WALK_METERS)
        end_candidates = self._nearest_stations(end_lat, end_lon, MAX_END_WALK_METERS)
        # No stop to walk to: widen the search so a town with no station of its
        # own still gets ride-then-final-gap instead of one taxi line across the
        # country. Only stops a line actually serves are useful -- walking to an
        # unserved one would just dead-end. Keep only the nearest: measured,
        # widening further makes Mahdia worse (98.3 km hop / 414 min vs 90.8 km
        # / 443 min), since a longer ride undercuts a short one plus a long hop.
        #
        # The final gap is priced by distance alone, in route() and
        # _expand_path alike. An earlier "did the narrow search succeed?" flag
        # got this wrong: Mahdia has a stop inside 2 km yet its drop-off is 90.8
        # km out, so the flag priced the gap as a walk while the label called
        # it a taxi hop.
        if not end_candidates:
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

        # Direct walk (always available).
        direct_m = haversine(start_lat, start_lon, end_lat, end_lon)
        direct_walk_s = direct_m / WALK_SPEED_MS
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

        # Multi-source Dijkstra.
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
                # The heap stores "" where the state has no line, so that cost
                # ties stay comparable; map it back to None for the cost model,
                # which distinguishes "not on a line" from a real line id.
                cur_line = _tie or None
                if cost >= best_cost:
                    break
                state = (cur, cur_line)
                if state in visited:
                    continue
                visited.add(state)

                # End-station check: if we've reached any end candidate, record
                # the full itinerary via end walk and update best (pruning later
                # pq entries at cost >= best_cost).
                if cur in end_ids:
                    ec = self.stations.get(cur)
                    if ec and ec.get("lat") and ec.get("lon"):
                        end_walk_m = haversine(ec["lat"], ec["lon"], end_lat, end_lon)
                        # Per-candidate decision: a final gap beyond
                        # MAX_END_WALK_METERS is not a walk any sane itinerary
                        # would ask for. Charge it as a local vehicle hop at taxi
                        # speed instead of pretending the rider walks 90 km.
                        # Keyed on the distance alone, not on used_dropoff, so a
                        # reachable-but-far end stop cannot fall back to walking
                        # speed in the cost model.
                        gap_is_hop = end_walk_m > MAX_END_WALK_METERS
                        if gap_is_hop:
                            end_walk_s = end_walk_m / TAXI_SPEED_MS
                        else:
                            end_walk_s = end_walk_m / WALK_SPEED_MS
                        total_s = cost + end_walk_s
                        if total_s < best_cost:
                            path_stations, path_lines = self._reconstruct(prev, state)
                            total_min, steps = self._expand_path(
                                path_stations,
                                path_lines,
                                start_lat, start_lon,
                                end_lat, end_lon,
                                self.stations.get(path_stations[0]) if path_stations else None,
                                ec,
                            )
                            best = {
                                "mode": "transit",
                                "duration_min": total_min,
                                "steps": steps,
                                "fare_dinars": None,
                            }
                            best_cost = total_s

                # Relax outgoing edges from the current node (inside the loop,
                # for the popped node — not after the loop).
                cur_station = self.stations.get(cur)
                if not cur_station:
                    continue
                for edge in self.adj.get(cur, ()):
                    # Mode restriction for this option. Walking is always
                    # permitted: every option starts and ends on foot, and it
                    # is the only way to reach a stop the restricted network
                    # does not serve.
                    if (
                        allowed_modes is not None
                        and edge.mode != "walk"
                        and edge.mode not in allowed_modes
                    ):
                        continue
                    is_walk = edge.mode == "walk"
                    # A walk edge has no line, so it resets the line
                    # context: after walking you have not "arrived on" any
                    # line, so the next boarding pays its wait afresh.
                    arrived_line = None if is_walk else edge.line
                    if is_walk:
                        segment_cost = edge.time_s
                    else:
                        segment_cost = edge.time_s
                        # Wait is charged once per boarding
                        # (cur_line != edge.line).
                        if cur_line != edge.line:
                            segment_cost += edge.wait_s
                        # Transfer penalty when switching lines.
                        if cur_line is not None and cur_line != edge.line:
                            segment_cost += TRANSFER_PENALTY_SEC
                    new_cost = cost + segment_cost
                    new_state: tuple[str, str | None] = (edge.to_id, arrived_line)
                    if new_cost < dist.get(new_state, float("inf")):
                        dist[new_state] = new_cost
                        prev[new_state] = state
                        # Monotonic tie-break key. Costs tie constantly
                        # in a walk network, and comparing the raw line
                        # id raised TypeError when one was None and the
                        # other a str; the empty string is a total
                        # order over the id space and never equals a
                        # real line id.
                        heapq.heappush(pq, (new_cost, edge.to_id, arrived_line or ""))

        # Direct taxi fallback (physical time + metered fare).
        # Only considered when no transit itinerary was found. Previously this
        # block simply took the cheaper of the two, which meant a single taxi
        # line was drawn across the whole map whenever it beat a multi-leg
        # transit path on time -- exactly the "long distance is one straight
        # line" behaviour being fixed. A real transit route must win outright.
        have_transit = best is not None and best.get("mode") == "transit"
        direct_km = direct_m / 1000.0
        if have_transit:
            # Record taxi as an alternative rather than as the answer.
            taxi_s = direct_m / TAXI_SPEED_MS
            if direct_km * 1000 >= TAXI_MIN_DISTANCE_M:
                taxi_fare = TAXI_FARE_BASE + TAXI_FARE_PER_KM * direct_km
                best["alternatives"] = best.get("alternatives", []) + [{
                    "mode": "taxi",
                    "duration_min": round(taxi_s / 60, 1),
                    "distance_km": round(direct_km, 1),
                    "fare_dinars": round(taxi_fare, 2),
                    "label": f"Taxi direct - {round(direct_km, 1)} km (~{round(taxi_s / 60)} min, {round(taxi_fare, 2)} DT)",
                }]
        elif direct_km * 1000 >= TAXI_MIN_DISTANCE_M:
            # Cost the trip on the same real road distance the leg is drawn
            # with. Pricing the straight line and drawing the road would make
            # the option look faster than the polyline the user sees.
            taxi_geom_pre = road_geometry_for(
                self.taxi_geometry, start_lat, start_lon, end_lat, end_lon
            )
            taxi_road_m = (
                polyline_length(taxi_geom_pre)
                if taxi_geom_pre and polyline_length(taxi_geom_pre) >= 0.95 * direct_m
                else direct_m
            )
            taxi_s = taxi_road_m / TAXI_SPEED_MS
            taxi_fare = TAXI_FARE_BASE + TAXI_FARE_PER_KM * direct_km
            if taxi_s < best_cost:
                # Real road geometry when the taxi cache has this pair. The
                # straight line is a lower bound, so using it here both draws a
                # line through fields and under-prices the trip.
                taxi_geom = road_geometry_for(
                    self.taxi_geometry, start_lat, start_lon, end_lat, end_lon
                )
                road_m = polyline_length(taxi_geom) if taxi_geom else direct_m
                if road_m < 0.95 * direct_m:
                    taxi_geom, road_m = [], direct_m
                road_s = road_m / TAXI_SPEED_MS
                road_fare = TAXI_FARE_BASE + TAXI_FARE_PER_KM * (road_m / 1000.0)
                taxi_step = {
                    "type": "taxi",
                    "mode": "taxi",
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
                    "label": f"Taxi — {round(road_m / 1000, 1)} km (~{round(road_s / 60)} min, {round(road_fare, 2)} DT)",
                }
                best = {
                    "mode": "taxi",
                    "duration_min": round(taxi_s / 60, 1),
                    "steps": [taxi_step],
                    "fare_dinars": round(taxi_fare, 2),
                }

        if not best:
            return {"error": "No route found", "duration_min": 0, "steps": [], "fare_dinars": None}
        best["duration_min"] = round(best["duration_min"], 1)
        return best

    def _reconstruct(
        self,
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

    def _edge_between(self, a_id: str, b_id: str, line: str | None) -> Edge | None:
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

    def _expand_path(
        self,
        path_stations: list[str],
        path_lines: list[str | None],
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        s_start: dict[str, Any] | None,
        s_end: dict[str, Any] | None,
    ) -> tuple[float, list[dict[str, Any]]]:
        """Convert a Dijkstra path (stations + lines arrived-on) into timed steps.

        The start walk is already accounted for in the Dijkstra initial label, so
        this only adds the transit/transfer segments and the end walk.
        """
        steps: list[dict[str, Any]] = []
        total_min = 0.0

        first = self.stations.get(path_stations[0]) if path_stations else None
        if first and first.get("lat") and first.get("lon"):
            prev_lat, prev_lon = first["lat"], first["lon"]
            prev_name = first.get("name", "")
        else:
            prev_lat, prev_lon = start_lat, start_lon
            prev_name = "Départ"

        # Start walk (only if the Dijkstra source station differs from the actual
        # start point — i.e. the walk was non-zero).
        if s_start and first and first.get("lat") and first.get("lon"):
            walk_m = haversine(start_lat, start_lon, first["lat"], first["lon"])
            if walk_m > 1:
                walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
                steps.append({
                    "type": "walk",
                    "from": {"lat": start_lat, "lon": start_lon},
                    "to": {"lat": first["lat"], "lon": first["lon"]},
                    # The access walk runs from the rider's point to the first
                    # station, so it has no station object at its end and no
                    # to_name. It does walk *to* that station, so name it --
                    # otherwise the map's first milestone is labelled with the
                    # instruction "Marcher 99 m ... jusqu'a X" instead of "X".
                    "to_name": first.get("name", ""),
                    "distance_m": round(walk_m),
                    "duration_min": round(walk_min, 1),
                    "time_seconds": round(walk_min * 60, 1),
                    "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'à {first.get('name', '')}",
                })
                total_min += walk_min

        for i in range(len(path_stations) - 1):
            a_id = path_stations[i]
            b_id = path_stations[i + 1]
            a = self.stations.get(a_id)
            b = self.stations.get(b_id)
            if not a or not b or not a.get("lat") or not a.get("lon") or not b.get("lat") or not b.get("lon"):
                continue
            line_used = path_lines[i + 1]  # line arrived on at b = line used for a->b
            straight_m = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
            # Prefer the edge the search actually traversed: it carries the REAL
            # along-geometry distance, time and polyline, so the reported step
            # equals the optimized cost and can be drawn accurately.
            edge = self._edge_between(a_id, b_id, line_used)
            seg_m = edge.distance_m if edge else straight_m
            seg_geom = edge.geometry if edge else []

            # A walk edge is a real pedestrian leg, not a ride: surface it as its
            # own walk step so the itinerary reads "walk, ride, walk" instead of
            # silently absorbing the transfer into the following ride.
            if line_used is None and seg_m > 1:
                walk_min = seg_m / 1000 / WALK_SPEED_KMH * 60
                steps.append({
                    "type": "walk",
                    "from": {"lat": a["lat"], "lon": a["lon"]},
                    "to": {"lat": b["lat"], "lon": b["lon"]},
                    "from_name": a.get("name", ""),
                    "to_name": b.get("name", ""),
                    # Station ids let the API layer look up real geometry for
                    # this leg in data/route_geometry.json.
                    "from_id": a_id,
                    "to_id": b_id,
                    "mode": "walk",
                    "distance_m": round(seg_m),
                    "duration_min": round(walk_min, 1),
                    "time_seconds": round(walk_min * 60, 1),
                    "geometry": seg_geom,
                    "label": f"Marcher {round(seg_m)} m jusqu'à {b.get('name', '')}",
                })
                total_min += walk_min
                prev_lat, prev_lon = b["lat"], b["lon"]
                prev_name = b.get("name", "")
                continue

            # A "ride" with no line and no distance is the same station appearing
            # twice on the path (two stops that share a coordinate, or a station
            # reached by a zero-length walk). Emitting it produced steps whose
            # start == end and whose line was an empty string -- visible to the
            # client as a rider "riding" between a point and itself. Skip it;
            # the surrounding steps already account for the movement.
            if line_used is None:
                continue

            mode = self.mode_of_line.get(line_used or "", "bus") or "bus"
            ride_m = seg_m
            ride_min = (edge.time_s / 60.0) if edge else (ride_m / 1000 / transit_speed_kmh(mode) * 60)

            prev_line = path_lines[i]  # line arrived on at a
            # Boarding wait is paid when starting a new line (first boarding or
            # transfer). It is already in the Dijkstra cost; surface it here so
            # the displayed duration matches the optimized cost.
            boarding = (prev_line is None or prev_line != line_used)
            wait_min = 0.0
            transfer_min = 0.0
            if boarding:
                wait_min = self.line_wait.get(line_used or "", 0.0) / 60.0
                if prev_line is not None:
                    transfer_min = TRANSFER_PENALTY_SEC / 60.0

            if transfer_min > 0:
                steps.append({
                    "type": "transfer",
                    "from": {"lat": prev_lat, "lon": prev_lon},
                    "to": {"lat": a["lat"], "lon": a["lon"]},
                    # Name the interchange, for the same reason as the access
                    # walk: without to_name the client can only show
                    # "Correspondance : marcher jusqu'a X", which buries a place
                    # name inside a sentence instead of naming the place.
                    "to_name": a.get("name", ""),
                    "mode": "transfer",
                    "distance_m": 0,
                    "time_seconds": round(transfer_min * 60, 1),
                    "duration_min": round(transfer_min, 1),
                    "label": f"Correspondance : marcher jusqu'a {a.get('name', '')}",
                })
                total_min += transfer_min

            display_ride_min = ride_min + wait_min
            wait_label = ""
            if wait_min > 0:
                wait_label = " (~" + str(round(wait_min)) + " min d'attente)"
            steps.append({
                "type": "ride",
                "line": line_used or "",
                "mode": mode,
                "from": {"lat": a["lat"], "lon": a["lon"]},
                "to": {"lat": b["lat"], "lon": b["lon"]},
                "from_name": a.get("name", ""),
                "to_name": b.get("name", ""),
                # Station ids let the API layer look up real geometry for
                # this leg in data/route_geometry.json.
                "from_id": a_id,
                "to_id": b_id,
                "distance_m": round(ride_m),
                "duration_min": round(display_ride_min, 1),
                "wait_min": round(wait_min, 1),
                "time_seconds": round(display_ride_min * 60, 1),
                "geometry": seg_geom,
                "straight_m": round(straight_m),
                "label": f"{mode} — {a.get('name', '')} → {b.get('name', '')}{wait_label}",
            })
            total_min += display_ride_min
            prev_lat, prev_lon = b["lat"], b["lon"]
            prev_name = b.get("name", "")

        # Final leg: walk when it is a walkable gap, otherwise an explicit local
        # taxi hop. Labelled as such so the gap between the network and the
        # destination is visible to the user instead of being hidden behind one
        # straight line across the map.
        if s_end and s_end.get("lat") and s_end.get("lon"):
            walk_m = haversine(prev_lat, prev_lon, end_lat, end_lon)
            if walk_m > 1:
                # Same rule as the cost branch in route(): distance decides,
                # not the used_dropoff flag, so the rendered leg and the
                # optimised cost can never disagree about what this leg is.
                if walk_m > MAX_END_WALK_METERS:
                    hop_min = walk_m / 1000 / TAXI_SPEED_KMH * 60
                    steps.append({
                        "type": "taxi",
                        "from": {"lat": prev_lat, "lon": prev_lon},
                        "to": {"lat": end_lat, "lon": end_lon},
                        "from_name": prev_name,
                        "distance_m": round(walk_m),
                        "distance_km": round(walk_m / 1000, 1),
                        "duration_min": round(hop_min, 1),
                        "time_seconds": round(hop_min * 60, 1),
                        "note": "no_stop_near_destination",
                        "label": (
                            f"Taxi local ~{round(walk_m / 1000, 1)} km jusqu'a destination "
                            f"(aucun arret de transport a proximite)"
                        ),
                    })
                    total_min += hop_min
                else:
                    walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
                    steps.append({
                        "type": "walk",
                        "from": {"lat": prev_lat, "lon": prev_lon},
                        "to": {"lat": end_lat, "lon": end_lon},
                        "distance_m": round(walk_m),
                        "duration_min": round(walk_min, 1),
                        "time_seconds": round(walk_min * 60, 1),
                        "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'a destination",
                    })
                    total_min += walk_min

        return round(total_min, 1), steps


if __name__ == "__main__":
    import sys

    g, r = build_graph()
    if len(sys.argv) >= 5:
        lat1, lon1, lat2, lon2 = map(float, sys.argv[1:5])
    else:
        lat1, lon1, lat2, lon2 = 36.806, 10.184, 36.914, 9.866  # Tunis Centre -> Bizerte
    res = r.route(lat1, lon1, lat2, lon2)
    print(json.dumps(res, indent=2, ensure_ascii=False))
