"""Great-circle geometry over [lat, lon] points."""
from __future__ import annotations

import math
from typing import Any, Sequence

EARTH_RADIUS_M = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def polyline_length(pts: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        total += haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
    return total


def oriented_geometry(entry: dict[str, Any], from_id: str, to_id: str) -> list[list[float]]:
    """Cached polyline between two stations, in travel order.

    Caches key a segment by the unordered pair min|max and store the polyline
    min -> max, so a step running the other way gets it reversed. [] when the
    entry has no usable polyline.
    """
    pts = entry.get("geometry") or []
    if len(pts) < 2:
        return []
    return list(reversed(pts)) if from_id > to_id else list(pts)
