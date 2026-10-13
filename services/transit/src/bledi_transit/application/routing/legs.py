"""Geometry for single legs: live network paths first, caches second."""
from __future__ import annotations

from typing import Any

from bledi_transit.application.ports import PathGeometry, Polyline
from bledi_transit.domain.geo import haversine_m, polyline_length


class NoPathGeometry:
    """No live network: every leg falls back to the caches."""

    def road(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float, mode: str) -> None:
        return None

    def rail(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> None:
        return None

    def foot_bridges(self, a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> list[Polyline]:
        return []


def resolve_walk_geometry(
    paths: PathGeometry,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
    fallback: Polyline | None = None,
) -> tuple[Polyline, float]:
    """Real pedestrian geometry for one walk leg, computed on demand.

    Returns (geometry, distance_m). Falls back, in order: the live foot graph,
    any precomputed cache polyline, a bridge through nearby connected foot
    nodes, then the straight line. The distance is the real along-geometry
    length whenever a real path was found, so the number in the itinerary
    matches the line the user sees.

    The bridge fixes the 125 m central-Tunis walk where both endpoints sit in
    genuinely disconnected foot components but a nearby through-street node
    connects them.

    Called per leg rather than for all 12 736 station pairs at startup: a live
    A* per pair would cost minutes of process start-up time, and a user only
    ever sees a handful of walks.
    """
    straight = haversine_m(a_lat, a_lon, b_lat, b_lon)
    live = paths.road(a_lat, a_lon, b_lat, b_lon, "foot")
    if live is not None and live[1] >= 0.95 * straight:
        return live[0], live[1]
    if fallback and len(fallback) >= 2:
        cached_m = polyline_length(fallback)
        if cached_m >= 0.95 * straight:
            return list(fallback), cached_m
    if straight <= 2000:
        best: Polyline | None = None
        best_m = float("inf")
        for geom in paths.foot_bridges(a_lat, a_lon, b_lat, b_lon):
            total_m = polyline_length(geom)
            if total_m < best_m and total_m >= 0.5 * straight:
                best, best_m = geom, total_m
        if best is not None and best_m >= 0.95 * straight:
            return best, best_m
    return [[a_lat, a_lon], [b_lat, b_lon]], straight


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
) -> Polyline:
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
