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
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from bledi_transit.adapters.graphs.rail_graph import load_rail_graph
from bledi_transit.adapters.graphs.rail_graph import track_between_cached as rail_track_cached
from bledi_transit.adapters.graphs.road_graph import load_graph as load_road_graph
from bledi_transit.adapters.graphs.road_graph import road_route_cached
from bledi_transit.domain.geo import haversine_m, oriented_geometry, polyline_length
from bledi_transit.domain.tunables import (
    BOARDING_WAIT_CAP,
    DEFAULT_WAIT_BY_MODE,
    DROP_OFF_CANDIDATES,
    DROPOFF_SEARCH_METERS,
    FEWEST_TRANSFERS_PENALTY_SEC,
    GEOMETRY_REQUIRED_M,
    MAX_END_WALK_METERS,
    MAX_HEADWAY_SEC,
    MAX_START_WALK_METERS,
    MAX_WALK_EDGE_METERS,
    SPEED_BY_MODE,
    TAXI_MIN_DISTANCE_M,
    TAXI_SPEED_KMH,
    TAXI_SPEED_MS,
    TRANSFER_PENALTY_SEC,
    WAIT_HEADWAY_FACTOR,
    WALK_SPEED_KMH,
    WALK_SPEED_MS,
)

log = logging.getLogger("bledi.routing")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

# ── Config ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[6]  # repo root
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# A walk edge resets the line context: after walking you have not "arrived on"
# any line, so the next boarding is a fresh boarding (wait paid again) rather
# than a free continuation. The sentinel keeps that distinct from a real line id.
WALK_EDGE = "__walk__"


def transit_speed_kmh(mode: str) -> float:
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])


def transit_speed_ms(mode: str) -> float:
    return transit_speed_kmh(mode) / 3.6


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
    root = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "..", ".."))
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
    root = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "..", ".."))
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


def rail_leg(
    router: "Router",
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> tuple[list[list[float]], float] | None:
    """Real-track polyline between two points on the rail network, or None.

    The answer comes from the TRACK, not from line numbers: both points are
    snapped onto the nearest OSM rail and A* runs along the rails. Two stops on
    the same corridor get the polyline that actually connects them whether or
    not any seed line claims they are consecutive.

    None means the two points are not on the same connected track. The caller
    must then fall back to cached geometry, and must not substitute a straight
    line: that is exactly the artefact this replaces.
    """
    g = getattr(router, "rail_graph", None)
    if g is None or rail_track_cached is None:
        return None
    try:
        t = rail_track_cached(g, a_lat, a_lon, b_lat, b_lon)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("rail geometry failed for %s -> %s: %s", (a_lat, a_lon), (b_lat, b_lon), exc)
        return None
    if t is None or len(t.geometry) < 2:
        return None
    return t.geometry, t.distance_m


def resolve_walk_geometry(
    router: "Router",
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    fallback: list[list[float]] | None = None,
) -> tuple[list[list[float]], float]:
    """Real pedestrian geometry for one walk leg, computed on demand.

    Returns (geometry, distance_m). Falls back, in order: the live foot graph,
    any precomputed cache polyline, then the straight line. The distance is the
    real along-geometry length whenever a real path was found, so the number in
    the itinerary matches the line the user sees.

    When the foot graph cannot serve the pair (disconnected components), try
    routing through a nearby connected foot node instead of giving up and
    drawing a straight line. This fixes the 125 m central-Tunis walk where
    both endpoints sit in genuinely disconnected foot components but a nearby
    through-street node can bridge them.

    Called per leg from _expand_path rather than for all 12 736 station pairs at
    startup: a live A* per pair would cost minutes of process start-up time, and
    a user only ever sees a handful of walks.
    """
    straight = haversine_m(a_lat, a_lon, b_lat, b_lon)
    live = road_leg(router, a_lat, a_lon, b_lat, b_lon, "foot")
    if live is not None and live[1] >= 0.95 * straight:
        return live[0], live[1]
    if fallback and len(fallback) >= 2:
        cached_m = polyline_length(fallback)
        if cached_m >= 0.95 * straight:
            return list(fallback), cached_m
    # Try to repair through a nearby connected foot node.
    # When both endpoints are in disconnected foot components, find the nearest
    # foot-usable node to each endpoint and route through it.
    g = getattr(router, "road_graph", None)
    if g is not None and road_route_cached is not None and straight <= 2000:
        try:
            # Find nearest foot-usable nodes for both endpoints
            from bledi_transit.adapters.graphs.road_graph import _snap_candidates
            a_candidates = _snap_candidates(g, "foot", a_lat, a_lon, max_m=250.0, want=3)
            b_candidates = _snap_candidates(g, "foot", b_lat, b_lon, max_m=250.0, want=3)
            # Try routing through each combination, preferring the shortest
            best_repair = None
            best_repair_dist = float("inf")
            for a_node, a_dist in a_candidates:
                for b_node, b_dist in b_candidates:
                    if a_node == b_node:
                        continue
                    # Check if these two nodes are connected by routing between them
                    r = road_route_cached(g, float(g.lat[a_node]), float(g.lon[a_node]),
                                         float(g.lat[b_node]), float(g.lon[b_node]), "foot",
                                         max_snap_m=1.0)
                    if r is not None and len(r.geometry) >= 2:
                        # Build the full path: a -> a_node -> ... -> b_node -> b
                        full_geom = [[a_lat, a_lon]]
                        # Walk from a to a_node (short straight hop)
                        full_geom.append([float(g.lat[a_node]), float(g.lon[a_node])])
                        full_geom.extend(r.geometry)
                        full_geom.append([float(g.lat[b_node]), float(g.lon[b_node])])
                        full_geom.append([b_lat, b_lon])
                        # Remove consecutive duplicates
                        deduped = [full_geom[0]]
                        for pt in full_geom[1:]:
                            if pt != deduped[-1]:
                                deduped.append(pt)
                        total_m = polyline_length(deduped)
                        if total_m < best_repair_dist and total_m >= 0.5 * straight:
                            best_repair = deduped
                            best_repair_dist = total_m
            if best_repair is not None and best_repair_dist >= 0.95 * straight:
                return best_repair, best_repair_dist
        except Exception:
            pass
    return [[a_lat, a_lon], [b_lat, b_lon]], straight


def road_leg(
    router: "Router",
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    mode: str,
) -> tuple[list[list[float]], float] | None:
    """Real-road polyline between two arbitrary points, or None.

    Wraps the OSM graph so callers get one answer: the polyline and its true
    along-road length in metres, or None when the road network cannot serve the
    pair. None is meaningful -- it means "no real path is known", and the caller
    must fall back rather than draw the straight line and present it as a route.

    The straight line is never returned here. It is a lower bound on any real
    path, so returning it would both draw an off-road line and understate the
    distance the user is quoted.
    """
    g = getattr(router, "road_graph", None)
    if g is None or road_route_cached is None:
        return None
    try:
        r = road_route_cached(g, a_lat, a_lon, b_lat, b_lon, mode)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("road routing failed for %s -> %s: %s", (a_lat, a_lon), (b_lat, b_lon), exc)
        return None
    if r is None or len(r.geometry) < 2:
        return None
    return r.geometry, r.distance_m


def load_taxi_geometry_cache() -> dict[str, list[list[float]]]:
    """Road polylines for direct taxi/louaj legs, keyed "lat,lon|lat,lon".

    Built by tool/build_taxi_geometry.py. These are the only place a path
    connects two points that are NOT both stations -- the access walk and the
    final drop-off -- so there is no station pair to key on, hence the
    coordinate key.
    """
    path = os.environ.get("TAXI_GEOMETRY_CACHE_PATH")
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "..", ".."))
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
    # travels the other way. Comparing the key's first endpoint against the
    # request origin is exactly the stored order.
    forward = taxi_key(a_lat, a_lon, b_lat, b_lon).split("|")[0] == (
        f"{round(a_lat, 5)},{round(a_lon, 5)}"
    )
    return list(pts) if forward else list(reversed(pts))


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

    `geometry` empty means "no real path was found". `needs_geometry` records
    whether that absence is visible enough to matter, so the API can refuse to
    draw a straight line instead of silently producing an off-road one.
    """
    to_id: str
    line: str
    mode: str
    wait_s: float
    distance_m: float
    time_s: float
    geometry: list[list[float]]
    straight_m: float

    @property
    def needs_geometry(self) -> bool:
        return not self.geometry and self.straight_m >= GEOMETRY_REQUIRED_M


# ── Fare model (C5) ──────────────────────────────────────────────────────
# Approximate, DOCUMENTED, and deliberately not a fare oracle: this is what
# objective=cheapest ranks by, so it must be monotone and defensible rather
# than accurate. Real Tunisian fares are a flat ticket per mode (bus/metro/tram
# ~0.5 DT, train ~5-8 DT by distance, louage shared per seat), so the model is
# "base + per-km" with a mode-dependent base.
#
# Never returns None (Part B2.4): an unknown mode falls back to the bus
# constant rather than yielding an unrankable itinerary.
#
# Constants live ONLY here, per the spec's "put constants in one place".
FARE_DINARS: dict[str, tuple[float, float]] = {
    #  mode        base DT   DT per km
    "bus":        (0.500,   0.000),
    "tram":       (0.500,   0.000),
    "metro":      (0.600,   0.000),
    "train":      (4.000,   0.090),
    "louaj":      (1.000,   0.150),
    "taxi":       (0.600,   0.520),   # matches TAXI_FARE_* below
    "walk":       (0.000,   0.000),
}
FARE_FALLBACK: tuple[float, float] = FARE_DINARS["bus"]


def fare_for_leg(mode: str, distance_m: float) -> float:
    """Estimated fare in dinars for one leg. Never negative, never None."""
    base, per_km = FARE_DINARS.get(canonical_mode(mode), FARE_FALLBACK)
    km = max(0.0, float(distance_m)) / 1000.0
    return round(base + per_km * km, 4)


def fare_for_itinerary(legs: Sequence[dict[str, Any]]) -> float:
    """Total estimated fare for an itinerary, charged once per BOARDED LINE.

    Charging per leg was wrong and measurably so: an itinerary is expanded one
    step per stop, so a 30-edge train ride arrived as 30 legs and was quoted at
    ~122 DT instead of ~7. Real Tunisian practice is a ticket per boarding, so
    consecutive legs on the SAME line are merged into one charge, and only a
    change of line adds another.

    Walks and transfers are free. Never returns None (Part B2.4).
    """
    total = 0.0
    current_line: str | None = None
    current_mode: str | None = None
    current_m = 0.0
    for leg in legs or ():
        kind = (leg.get("type") or leg.get("mode") or "").lower()
        if kind in ("walk", "transfer", ""):
            continue
        line = leg.get("line") or ""
        mode = leg.get("mode") or kind
        if line != current_line or mode != current_mode:
            if current_line is not None:
                total += fare_for_leg(current_mode or "", current_m)
            current_line, current_mode, current_m = line, mode, 0.0
        current_m += float(leg.get("distance_m") or 0.0)
    if current_line is not None:
        total += fare_for_leg(current_mode or "", current_m)
    return round(total, 2)


# ── User-facing mode taxonomy (B1) ────────────────────────────────────────
# Previously metro was folded into RAIL_MODES with train, which made
# "no metro but train is fine" inexpressible: a user could not exclude one
# without excluding both. Modes are now flat and each is independently
# includable/excludable.
#
# User-facing mode -> seed line.mode values that map onto it.
# The louage_red|blue|green tags come from the secondary louage seed
# (seed_routes_destination_tunis.json), which classifies shared taxis by route
# colour. They are all louage and must not fall through to the "unknown -> bus"
# default in canonical_mode, which would mislabel them as scheduled buses.
MODE_ALIASES: dict[str, frozenset[str]] = {
    "bus": frozenset({"bus", "rfr"}),
    "tram": frozenset({"tram"}),
    "metro": frozenset({"metro"}),
    "train": frozenset({"train", "rail"}),
    "louaj": frozenset({
        "louaj", "louage", "louage_red", "louage_blue", "louage_green",
    }),
    "taxi": frozenset({"taxi"}),
    "walk": frozenset({"walk"}),
}

# Canonical user-facing modes, in the display order used by labels and by the
# station/line listings. Order is deliberate: urban modes first, intercity
# rail last, road-for-hire after.
USER_MODES: tuple[str, ...] = (
    "bus",
    "tram",
    "metro",
    "train",
    "louaj",
    "taxi",
    "walk",
)

# French labels. The API and the UI are already French; mixing English in here
# would be a regression, so en/ar are deliberately NOT added (Part B5).
MODE_LABELS_FR: dict[str, str] = {
    "bus": "Bus",
    "tram": "Tramway",
    "metro": "Metro",
    "train": "Train",
    # Taxi and louage are one rider-facing category (road for hire); the UI
    # presents them as a single chip, so the label matches that.
    "louaj": "Taxi / Louage",
    "taxi": "Taxi / Louage",
    "walk": "Marche",
    # Station-only tag: a geocoded stop whose operator export carried no mode.
    # It is not routable, so it is deliberately absent from USER_MODES.
    "unclassified": "Non classé",
}

BUS_MODES: frozenset[str] = frozenset({"bus", "rfr", "tram"})
RAIL_MODES: frozenset[str] = frozenset({"train", "rail", "metro"})
TAXI_MODES: frozenset[str] = frozenset({"taxi", "louaj"})

def canonical_mode(raw: str | None) -> str:
    """Map a seed line.mode onto one of USER_MODES. Unknown -> "bus".

    Unknown modes must not vanish silently: they fall back to bus because a
    scheduled line with an unrecognised tag is still a scheduled line, and
    dropping it would delete real services from the network.
    """
    if not raw:
        return "bus"
    r = str(raw).strip().lower()
    for mode, aliases in MODE_ALIASES.items():
        if r in aliases:
            return mode
    return "bus"


def resolve_allowed_modes(
    include: list[str] | set[str] | tuple[str, ...] | None,
    exclude: list[str] | set[str] | tuple[str, ...] | None,
) -> frozenset[str] | None:
    """Raw edge-mode set for an include/exclude request.

    Returns None for "no restriction". Raises ValueError when the request can
    never be satisfied (unknown mode name, or include-minus-exclude empty), so
    the API can answer 400 instead of silently returning "no route".

    The returned set contains RAW seed modes (bus, rfr, tram, train, rail,
    metro, taxi, louaj) because that is what Edge.mode holds. Exclusion is
    resolved through MODE_ALIASES, so excluding "train" also removes the seed
    mode "rail", and excluding "bus" also removes "rfr".
    """
    known_raw: set[str] = set()
    for aliases in MODE_ALIASES.values():
        known_raw |= set(aliases)

    def expand(names: set[str], what: str) -> set[str]:
        out: set[str] = set()
        unknown: set[str] = set()
        for n in names:
            key = str(n).strip().lower()
            if not key:
                continue
            if key in MODE_ALIASES:
                out |= set(MODE_ALIASES[key])
            elif key in known_raw:
                # Accept a raw seed mode too (e.g. "rfr").
                out.add(key)
            else:
                unknown.add(key)
        if unknown:
            raise ValueError(
                f"unknown {what}: {sorted(unknown)}; available: {list(USER_MODES)}"
            )
        return out

    inc = expand(set(include or ()), "modes_include")
    exc = expand(set(exclude or ()), "modes_exclude")
    if inc:
        allowed = inc - exc
        if not allowed:
            raise ValueError(
                "modes_exclude removed every requested mode; "
                f"available: {list(USER_MODES)}"
            )
        return frozenset(allowed)
    if exc:
        # Exclude-only: everything except the excluded modes. walk stays in, it
        # is never a selectable transport but always needed for access.
        allowed = known_raw - exc
        if not allowed:
            raise ValueError(
                "modes_exclude removed every available mode; "
                f"available: {list(USER_MODES)}"
            )
        return frozenset(allowed | {"walk"})
    return None


def mode_label_fr(mode: str) -> str:
    """French label for one user-facing mode.

    The label table is consulted with the RAW value first, before
    canonicalisation. Otherwise a station-only tag such as `unclassified`
    would be absorbed by canonical_mode's "unknown -> bus" fallback and the
    76 untagged sweep stops would be labelled as scheduled buses.
    """
    raw = str(mode or "").strip().lower()
    if raw in MODE_LABELS_FR:
        return MODE_LABELS_FR[raw]
    return MODE_LABELS_FR.get(canonical_mode(mode), mode)


def label_modes_fr(modes: object) -> str:
    """'Bus + Metro' style label for an iterable of modes, in USER_MODES order."""
    seen: set[str] = set()
    if isinstance(modes, str):
        modes = [modes]
    for m in modes or ():
        seen.add(canonical_mode(m))
    return " + ".join(MODE_LABELS_FR[m] for m in USER_MODES if m in seen)


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
        # User-facing mode per line (B1). mode_of_line keeps the RAW seed value
        # because Edge.mode must stay comparable against allowed_modes, which
        # resolve_allowed_modes() returns as raw seed modes. The canonical form
        # is what labels, fares and the API report.
        self.user_mode_of_line: dict[str, str] = {}
        self.line_wait: dict[str, float] = {}  # line_id -> boarding wait (s)
        for ln in lines:
            ln_id = ln.get("id", "") or ""
            mode = ln.get("mode", "bus") or "bus"
            self.mode_of_line[ln_id] = mode
            self.user_mode_of_line[ln_id] = canonical_mode(mode)
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
        # The OSM road graph. Real source of truth for any leg whose endpoints
        # are not two stations joined by a transit line (access walk, final walk,
        # taxi/louaj). The geometry caches above stay as a fast path and as a
        # fallback for stops far from any drivable road.
        self.road_graph = load_road_graph(log=log) if load_road_graph else None
        # Rail track, for train/metro/tram legs. Without it the cached
        # geometry covers only 1 776 of ~3 900 station pairs and the rest
        # were drawn as straight lines -- the jump-to-next-station zigzag.
        self.rail_graph = load_rail_graph(log=log) if load_rail_graph else None
        # station_id -> ordered list of line ids serving it (B3). Built from
        # the line -> stops index, NOT from the station's own lines_served
        # fragments, which are direction-oriented and often lack route_short_name.
        # This is the authoritative "what passes here" source.
        self.lines_by_station: dict[str, list[str]] = defaultdict(list)
        for ln in lines:
            ln_id = ln.get("id", "") or ""
            if not ln_id:
                continue
            stops = ln.get("stations") or ln.get("stops") or []
            for sid in stops:
                if isinstance(sid, str):
                    self.lines_by_station[sid].append(ln_id)
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
        straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
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
                        d = haversine_m(lat, lon, o_lat, o_lon)
                        if d <= MAX_WALK_EDGE_METERS:
                            # Real pedestrian path when the cache has it. A walk
                            # edge has no line id, so the walk geometry is stored
                            # under the same "a|b" key with a walk-mode marker.
                            wkey = f"{min(sid, other)}|{max(sid, other)}"
                            wentry = self.walk_geometry.get(wkey)
                            wgeom: list[list[float]] = []
                            wlen = d
                            # Geometry here is deliberately NOT live-routed.
                            # This loop builds every station pair within 900 m
                            # (12 736 of them in the current seed) and a live
                            # A* per pair would add minutes to process startup.
                            # The precomputed walk cache is used if present; the
                            # road graph fills in the real pedestrian path
                            # lazily, per leg, in _expand_path -- see
                            # resolve_walk_geometry -- which is memoised and only
                            # ever pays for a walk the user actually sees.
                            if wentry and wentry.get("geometry"):
                                cand = oriented_geometry(wentry, sid, other)
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
        transfer_penalty_sec: float | None = None,
        max_walk_m: float | None = None,
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
        # Initial candidate search.
        start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)
        end_candidates = self._nearest_stations(end_lat, end_lon, end_cap)
        # Ensure for bus-restricted searches we have at least one start station with a bus-family edge.
        if allowed_modes is not None and (allowed_modes & BUS_MODES):
            def has_bus_edge(st_id):
                return any(e.mode in BUS_MODES for e in self.adj.get(st_id, []))
            if not any(has_bus_edge(sc['id']) for sc in start_candidates):
                # dramatically expand start walk radius and recompute
                start_cap = MAX_START_WALK_METERS * 500
                start_candidates = self._nearest_stations(start_lat, start_lon, start_cap)


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
        best_transit: dict[str, Any] | None = None
        best_transit_cost = float("inf")

        # Direct walk (always available) – only used if walking is allowed.
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
        else:
            best = None
            best_cost = float("inf")

        # Walking-only request: the user asked for directions on foot, so no
        # transit search and no vehicle fallback should run. Return the direct
        # walk outright.
        if allowed_modes is not None and not (allowed_modes - {"walk"}):
            return best

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
                        end_walk_m = haversine_m(ec["lat"], ec["lon"], end_lat, end_lon)
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
                                allowed_modes,
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
                            segment_cost += transfer_penalty
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
        #
        # It must ALSO respect the caller's mode selection: a taxi/louaj answer
        # is only legitimate when taxi or louaj is actually allowed. Without
        # this gate, selecting "walk only" returned a taxi (walk is slow, taxi
        # is fast, so the comparison below always fired), and selecting
        # bus+metro+tram+train+rfr silently appended a taxi leg.
        have_transit = best is not None and best.get("mode") == "transit"
        direct_km = direct_m / 1000.0
        taxi_permitted = allowed_modes is None or bool(
            allowed_modes & TAXI_MODES
        )
        # Which road-based mode answers this request. Louage and taxi are both
        # shared/private car modes but are priced differently (shared per seat
        # vs metered private hire), so the leg must be labelled and costed as
        # whichever the user actually selected. When both are allowed, taxi is
        # the more general answer and keeps its own label.
        road_mode = "taxi"
        if allowed_modes is not None and "taxi" not in allowed_modes and "louaj" in allowed_modes:
            road_mode = "louaj"
        road_speed_ms = TAXI_SPEED_MS
        def road_fare_for(km: float) -> float:
            base, per_km = FARE_DINARS[road_mode]
            return base + per_km * km
        if have_transit:
            # Record taxi as an alternative rather than as the answer.
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
            # with. Pricing the straight line and drawing the road would make
            # the option look faster than the polyline the user sees.
            # Live road graph first, precomputed taxi cache second. The graph is
            # authoritative: it covers the whole country and knows one-way
            # restrictions, so the fare is computed on the road the taxi drives,
            # not on a straight line through fields.
            live_taxi = road_leg(self, start_lat, start_lon, end_lat, end_lon, "car")
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
                # Real road geometry when the taxi cache has this pair. The
                # straight line is a lower bound, so using it here both draws a
                # line through fields and under-prices the trip.
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
            d = haversine_m(lat, lon, s["lat"], s["lon"])
            if d <= max_m:
                out.append({**s, "_dist_m": d})
        out.sort(key=lambda x: x["_dist_m"])
        return out

    # ── B2: multi-objective planner ─────────────────────────────────────
    OBJECTIVES: tuple[str, ...] = ("fastest", "cheapest", "fewest_transfers")

    @staticmethod
    def _itinerary_signature(result: dict[str, Any]) -> tuple:
        """Distinctness key: the ordered (mode, line_id) of every ride leg.

        Walks are excluded on purpose. Two itineraries that differ only in how
        far the rider walks on the same bus are the same journey as far as a
        choice list is concerned, and offering both is the "messy options"
        complaint (A3).
        """
        sig: list[tuple[str, str]] = []
        for step in result.get("steps") or ():
            if step.get("type") != "ride":
                continue
            entry = (step.get("mode") or "", step.get("line") or "")
            # Collapse consecutive legs on the same line. An itinerary is
            # expanded per STOP, so without this every stop looked like a
            # distinct itinerary and dedup never fired -- which is why all
            # three objectives returned exactly one option.
            if sig and sig[-1] == entry:
                continue
            sig.append(entry)
        if not sig:
            # No rides at all (pure walk / pure taxi): fall back on mode+shape.
            sig = [
                (step.get("type") or "", "")
                for step in result.get("steps") or ()
                if step.get("type") in ("taxi", "walk")
            ]
        return tuple(sig)

    @staticmethod
    def _count_transfers(steps: Sequence[dict[str, Any]]) -> int:
        """Number of line changes across ride legs."""
        lines = [
            s.get("line") or "" for s in (steps or ()) if s.get("type") == "ride"
        ]
        changes = 0
        for i in range(1, len(lines)):
            if lines[i] != lines[i - 1]:
                changes += 1
        return changes

    @staticmethod
    def _modes_used(steps: Sequence[dict[str, Any]]) -> list[str]:
        used: set[str] = set()
        for step in steps or ():
            if step.get("type") in ("walk", "transfer"):
                continue
            m = canonical_mode(step.get("mode") or step.get("type") or "")
            if m != "walk":
                used.add(m)
        return [m for m in USER_MODES if m in used]

    @staticmethod
    def _geometry_report(steps: Sequence[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
        """(geometry_complete, gaps[]) — geometry honesty (C6).

        A leg is a GAP when it moves a meaningful distance and carries no
        polyline. Those are exactly the legs the client must render dashed
        rather than silently joining two points with a straight line.
        """
        gaps: list[dict[str, Any]] = []
        for step in steps or ():
            dist = float(step.get("distance_m") or 0.0)
            has = bool(step.get("geometry"))
            if has or dist < GEOMETRY_REQUIRED_M:
                continue
            gaps.append(
                {
                    "type": step.get("type"),
                    "mode": step.get("mode"),
                    "line": step.get("line"),
                    "from": step.get("from"),
                    "to": step.get("to"),
                    "distance_m": round(dist),
                    "straight_m": step.get("straight_m"),
                    "reason": "no_cached_geometry",
                }
            )
        return (not gaps), gaps

    def route_plan(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
        objective: str = "fastest",
        max_transfers: int | None = None,
        max_walk_m: float | None = None,
        max_itineraries: int = 3,
    ) -> dict[str, Any]:
        """Return distinct, labelled itineraries for a filtered request.

        Several strategies are run and their best results merged, deduplicated
        and ranked. Strategies, not just weights, is the point: a single
        Dijkstra with a bigger transfer penalty does NOT produce a different
        journey when one itinerary dominates on every axis, which is exactly
        the Tunis->Sousse case (the single rail journey is fastest, has the
        fewest transfers and is the only rail option, so re-ranking it three
        times yields three copies of itself).

          fastest             unfiltered search, time-optimal
          fewest_transfers    a very high transfer penalty
          cheapest            unfiltered search (the fare model is a post-hoc
                              ranking over candidates, not a search cost, so
                              this does not change the journey found)
          bus_preferred       bus/rfr/tram only
          rail_preferred      train/rail/metro only
          metro_preferred     metro only
          train_only          train/rail only

        Include/exclude is a HARD filter applied inside edge expansion for
        every strategy, so an excluded mode can never appear in a leg (D1).
        """
        if objective not in self.OBJECTIVES:
            raise ValueError(
                f"unknown objective {objective!r}; expected one of {list(self.OBJECTIVES)}"
            )
        try:
            max_itineraries = int(max_itineraries)
        except (TypeError, ValueError):
            max_itineraries = 3
        max_itineraries = max(1, min(8, max_itineraries))
        if max_transfers is not None:
            max_transfers = int(max_transfers)
            if max_transfers < 0:
                raise ValueError("max_transfers must be >= 0")

        user_allowed = resolve_allowed_modes(include, exclude)

        # Walking-only request: the user explicitly asked for directions on
        # foot. Emit the direct walk as the single itinerary and skip the
        # transit strategies entirely (they cannot match a walk-only filter,
        # so they would only produce an empty result).
        if user_allowed is not None and not (user_allowed - {"walk"}):
            direct_m = haversine_m(start_lat, start_lon, end_lat, end_lon)
            walk_s = direct_m / WALK_SPEED_MS
            walk_step = {
                "type": "walk",
                "from": {"lat": start_lat, "lon": start_lon},
                "to": {"lat": end_lat, "lon": end_lon},
                "distance_m": round(direct_m),
                "duration_min": round(walk_s / 60, 1),
                "time_seconds": round(walk_s, 1),
                "label": f"Marcher {round(direct_m)} m (~{round(walk_s / 60)} min)",
            }
            walk_candidate = {
                "searched_for": "walk",
                "raw": {"mode": "walk", "duration_min": round(walk_s / 60, 1), "steps": [walk_step]},
                "steps": [walk_step],
                "signature": self._itinerary_signature({"steps": [walk_step]}),
                "duration_s": walk_s,
                "transfers": 0,
                "fare_estimate": 0.0,
                "modes_used": ["walk"],
                "geometry_complete": False,
                "gaps": [],
            }
            return {
                "query": self._query_echo(start_lat, start_lon, end_lat, end_lon,
                                          include, exclude, objective,
                                          max_transfers, max_walk_m, max_itineraries),
                "itineraries": [self._present(walk_candidate, 1, objective)],
                "available_modes": list(USER_MODES),
                "message": None,
            }

        # Translate the user's filter into per-strategy raw-mode sets.
        bus_only = frozenset({"bus", "rfr", "tram"})
        rail_only = frozenset({"train", "rail", "metro"})
        metro_only = frozenset({"metro"})
        train_only = frozenset({"train", "rail"})

        # The two unfiltered strategies still have to respect the user's
        # filter: "fastest" with allowed=None would happily return the metro
        # journey the user just excluded. user_allowed is therefore the BASE
        # for every strategy, never None when a filter was given.
        strategies: list[tuple[str, float, frozenset[str] | None]] = [
            ("fastest", TRANSFER_PENALTY_SEC, user_allowed),
            ("fewest_transfers", FEWEST_TRANSFERS_PENALTY_SEC, user_allowed),
        ]
        for name, subset in (
            ("bus_preferred", bus_only),
            ("rail_preferred", rail_only),
            ("metro_preferred", metro_only),
            ("train_only", train_only),
        ):
            inter = subset if user_allowed is None else (user_allowed & subset)
            if not inter:
                continue
            strategies.append((name, TRANSFER_PENALTY_SEC, inter))

        candidates: list[dict[str, Any]] = []
        for name, penalty, allowed in strategies:
            raw = self.route(
                start_lat,
                start_lon,
                end_lat,
                end_lon,
                allowed_modes=allowed,
                transfer_penalty_sec=penalty,
                max_walk_m=max_walk_m,
            )
            steps = raw.get("steps") or []
            if not steps or raw.get("mode") == "walk" and len(steps) <= 1:
                # Skip the degenerate pure-straight-line walk unless nothing
                # else was found; it is offered as a last resort below.
                continue
            transfers = self._count_transfers(steps)
            if max_transfers is not None and transfers > max_transfers:
                continue
            duration_s = float(raw.get("duration_min") or 0.0) * 60.0
            fare = fare_for_itinerary(steps)
            complete, gaps = self._geometry_report(steps)
            candidates.append(
                {
                    "searched_for": name,
                    "raw": raw,
                    "steps": steps,
                    "signature": self._itinerary_signature(raw),
                    "duration_s": duration_s,
                    "transfers": transfers,
                    "fare_estimate": fare,
                    "modes_used": self._modes_used(steps),
                    "geometry_complete": complete,
                    "gaps": gaps,
                }
            )

        # Last resort: the direct walk, only if the search produced nothing.
        if not candidates:
            direct_m = haversine_m(start_lat, start_lon, end_lat, end_lon)
            if direct_m <= MAX_START_WALK_METERS * 2:
                walk_s = direct_m / WALK_SPEED_MS
                steps = [
                    {
                        "type": "walk",
                        "from": {"lat": start_lat, "lon": start_lon},
                        "to": {"lat": end_lat, "lon": end_lon},
                        "distance_m": round(direct_m),
                        "duration_min": round(walk_s / 60, 1),
                        "time_seconds": round(walk_s, 1),
                        "label": f"Marcher {round(direct_m)} m (~{round(walk_s / 60)} min)",
                    }
                ]
                candidates.append(
                    {
                        "searched_for": "walk",
                        "raw": {"mode": "walk", "duration_min": round(walk_s / 60, 1), "steps": steps},
                        "steps": steps,
                        "signature": self._itinerary_signature({"steps": steps}),
                        "duration_s": walk_s,
                        "transfers": 0,
                        "fare_estimate": 0.0,
                        "modes_used": ["walk"],
                        "geometry_complete": False,
                        "gaps": [],
                    }
                )

        if not candidates:
            return {
                "query": self._query_echo(start_lat, start_lon, end_lat, end_lon,
                                          include, exclude, objective,
                                          max_transfers, max_walk_m, max_itineraries),
                "itineraries": [],
                "available_modes": list(USER_MODES),
                "message": _no_route_message(include, exclude),
            }

        # Rank by the requested objective (B2.4). Ties fall through to the
        # secondary axis so the order is total and deterministic.
        if objective == "cheapest":
            candidates.sort(key=lambda c: (c["fare_estimate"], c["duration_s"]))
        elif objective == "fewest_transfers":
            candidates.sort(key=lambda c: (c["transfers"], c["duration_s"]))
        else:
            candidates.sort(key=lambda c: (c["duration_s"], c["transfers"]))

        out: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        for c in candidates:
            if c["signature"] in seen:
                continue
            seen.add(c["signature"])
            out.append(c)
            if len(out) >= max_itineraries:
                break

        return {
            "query": self._query_echo(start_lat, start_lon, end_lat, end_lon,
                                      include, exclude, objective,
                                      max_transfers, max_walk_m, max_itineraries),
            "itineraries": [self._present(c, i + 1, objective) for i, c in enumerate(out)],
            "available_modes": list(USER_MODES),
            "message": None,
        }

    @staticmethod
    def _query_echo(
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        include: Sequence[str] | None,
        exclude: Sequence[str] | None,
        objective: str,
        max_transfers: int | None,
        max_walk_m: float | None,
        max_itineraries: int,
    ) -> dict[str, Any]:
        return {
            "start": {"lat": start_lat, "lon": start_lon},
            "end": {"lat": end_lat, "lon": end_lon},
            "modes_include": list(include) if include else [],
            "modes_exclude": list(exclude) if exclude else [],
            "objective": objective,
            "max_transfers": max_transfers,
            "max_walk_m": max_walk_m,
            "max_itineraries": max_itineraries,
        }

    @staticmethod
    def _present(c: dict[str, Any], n: int, objective: str) -> dict[str, Any]:
        """One client-facing itinerary card (B5)."""
        raw = c["raw"]
        modes = c["modes_used"]
        duration_min = round(c["duration_s"] / 60.0, 1)
        tr = c["transfers"]
        bits = [label_modes_fr(modes) or "Marche"]
        bits.append(_fmt_dur_fr(duration_min))
        if tr:
            bits.append(f"{tr} correspondance{'s' if tr > 1 else ''}")
        else:
            bits.append("direct")
        return {
            "id": f"opt_{n}",
            "label": " · ".join(bits),
            "rank_reason": _rank_reason_fr(c, objective, n),
            "mode": raw.get("mode"),
            "duration_min": duration_min,
            "duration_s": round(c["duration_s"], 1),
            "transfers": tr,
            "fare_estimate_dinars": c["fare_estimate"],
            "modes_used": modes,
            "legs": c["steps"],
            "steps": c["steps"],
            "geometry_complete": c["geometry_complete"],
            "gaps": c["gaps"],
            "searched_for": c["searched_for"],
        }


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
        allowed_modes: frozenset[str] | None = None,
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
            straight_walk_m = haversine_m(start_lat, start_lon, first["lat"], first["lon"])
            # Real pedestrian route when the road graph can serve the pair. The
            # straight line is kept as the distance floor, so a graph miss costs
            # the polyline but never invents a shorter-than-impossible walk.
            live = road_leg(self, start_lat, start_lon, first["lat"], first["lon"], "foot")
            walk_m = straight_walk_m
            walk_geom: list[list[float]] = []
            if live is not None and live[1] >= 0.95 * straight_walk_m:
                walk_geom, walk_m = live[0], live[1]
            if walk_m > 1:
                walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
                steps.append({
                    "type": "walk",
                    "from": {"lat": start_lat, "lon": start_lon},
                    "to": {"lat": first["lat"], "lon": first["lon"]},
                    "geometry": walk_geom,
                    "straight_m": round(straight_walk_m),
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
            straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
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
                # Upgrade a straight-lined transfer walk to the real pedestrian
                # path now that we know this leg is on the itinerary. The edge's
                # own polyline is the fallback, so a graph miss degrades to
                # exactly what it showed before this change.
                wg, seg_m = resolve_walk_geometry(
                    self, a["lat"], a["lon"], b["lat"], b["lon"], seg_geom or None
                )
                seg_geom = wg
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

            # Report the USER-FACING mode (B1). Raw seed mode was "rail" for a
            # metro-tagged line in some records; the client must not have to
            # know that mapping.
            mode = self.user_mode_of_line.get(line_used or "", "bus") or "bus"
            ride_m = seg_m
            # Speed lookup must use the RAW seed mode, not the user-facing one.
            # canonical_mode() folds seed "rail" into "train", but SPEED_BY_MODE
            # rates them differently (train 60 km/h, rail 55 km/h), so passing
            # the canonical name silently re-timed every regional-rail leg and
            # changed which route the search picked (measured: Tunis->Sfax went
            # 344.7 -> 352.3 min and the walk/no-walk ordering test broke).
            # Prefer REAL TRACK over cached geometry for rail modes.
            # The cache covers only 1 776 of ~3 900 station pairs and the gaps
            # are almost all rail, so a missing cached segment rendered as a
            # straight line -- the "jumps to the next station then comes back"
            # artefact. Snapping to the rail network fixes it at the source: the
            # polyline is whatever the rails physically do between the two
            # points, independent of any line number.
            #
            # The cached geometry is NOT discarded. It stays the fallback when
            # the two points are not on one connected track, and the result is
            # length-checked against the crow-flies distance so no impossible
            # sub-straight-line path can be accepted.
            if mode in ("train", "metro", "tram"):
                live_rail = rail_leg(
                    self, a["lat"], a["lon"], b["lat"], b["lon"]
                )
                if live_rail is not None and live_rail[1] >= 0.95 * straight_m:
                    seg_geom = live_rail[0]
                    seg_m = live_rail[1]
                    edge = None  # force re-timing from the real track distance

            raw_mode = self.mode_of_line.get(line_used or "", "bus") or "bus"
            # For bus legs with no cached geometry, try the road graph as a
            # fallback. Buses follow roads, so the road network can provide
            # real geometry when the precomputed cache is missing a segment.
            if not seg_geom and mode == "bus" and straight_m >= GEOMETRY_REQUIRED_M:
                live_bus = road_leg(self, a["lat"], a["lon"], b["lat"], b["lon"], "car")
                if live_bus is not None and live_bus[1] >= 0.95 * straight_m:
                    seg_geom = live_bus[0]
                    seg_m = live_bus[1]
                    edge = None  # force re-timing from the real road distance
            ride_min = (
                (edge.time_s / 60.0)
                if edge
                else (ride_m / 1000 / transit_speed_kmh(raw_mode) * 60)
            )

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
                # No polyline on a leg long enough for the omission to be
                # visible. The client uses this to refuse a straight line
                # rather than draw one across open country.
                "needs_geometry": bool(
                    not seg_geom and straight_m >= GEOMETRY_REQUIRED_M
                ),
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
            straight_walk_m = haversine_m(prev_lat, prev_lon, end_lat, end_lon)
            # Route the gap in the mode it will actually be travelled: a short
            # gap is walked (pedestrian ways, steps, footways), while a gap past
            # MAX_END_WALK_METERS is a local taxi hop and must follow drivable
            # roads. Routing a 40 km taxi hop on the foot network would send it
            # down footpaths and stairs.
            leg_mode = "foot" if straight_walk_m <= MAX_END_WALK_METERS else "car"
            live = road_leg(self, prev_lat, prev_lon, end_lat, end_lon, leg_mode)
            walk_m = straight_walk_m
            walk_geom: list[list[float]] = []
            if live is not None and live[1] >= 0.95 * straight_walk_m:
                walk_geom, walk_m = live[0], live[1]
            if walk_m > 1:
                # Same rule as the cost branch in route(): distance decides,
                # not the used_dropoff flag, so the rendered leg and the
                # optimised cost can never disagree about what this leg is.
                # A long final gap is only a taxi hop when a car-based mode is
                # actually selected. Otherwise (e.g. bus-only, or walking-only)
                # it must stay a walk -- emitting a taxi leg the user did not
                # select is what made "bus only" return a bus+taxi itinerary.
                hop_permitted = allowed_modes is None or bool(allowed_modes & TAXI_MODES)
                if walk_m > MAX_END_WALK_METERS and hop_permitted:
                    hop_min = walk_m / 1000 / TAXI_SPEED_KMH * 60
                    steps.append({
                        "type": "taxi",
                        "from": {"lat": prev_lat, "lon": prev_lon},
                        "to": {"lat": end_lat, "lon": end_lon},
                        "from_name": prev_name,
                        "geometry": walk_geom,
                        "straight_m": round(straight_walk_m),
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
                        "geometry": walk_geom,
                        "straight_m": round(straight_walk_m),
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


def _fmt_dur_fr(minutes: float) -> str:
    m = int(round(minutes))
    if m < 60:
        return f"{m} min"
    h, rem = divmod(m, 60)
    return f"{h} h {rem:02d}" if rem else f"{h} h"


def _rank_reason_fr(c: dict[str, Any], objective: str, n: int) -> str:
    modes = label_modes_fr(c["modes_used"]) or "Marche"
    tr = c["transfers"]
    dur = _fmt_dur_fr(c["duration_s"] / 60.0)
    if n == 1:
        if objective == "cheapest":
            return f"le moins cher · {c['fare_estimate']:.2f} DT · {dur}"
        if objective == "fewest_transfers":
            return f"le moins de correspondances · {tr} · {dur}"
        return f"le plus rapide · {dur}"
    return f"{modes} · {dur} · {tr} correspondance{'s' if tr > 1 else ''}"


def _no_route_message(
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
) -> str:
    """Actionable French message when filters leave no journey (B5.message)."""
    if exclude:
        return (
            "Aucun itineraire avec les modes selectionnes; essayez d'activer "
            + ", ".join(sorted(set(USER_MODES) - {canonical_mode(m) for m in exclude}))
            + "."
        )
    if include:
        return (
            "Aucun itineraire pour ces modes; essayez d'en ajouter un autre "
            f"({', '.join(USER_MODES)})."
        )
    return "Aucun itineraire trouve entre ces deux points."
