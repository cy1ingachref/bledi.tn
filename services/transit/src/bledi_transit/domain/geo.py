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


def simplify(pts: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker on [[lat, lon]] pairs, tolerance in degrees."""
    if len(pts) < 3 or tol <= 0:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a0, a1 = pts[i][0], pts[i][1]
        s0, s1 = pts[j][0] - a0, pts[j][1] - a1
        seg_len = math.hypot(s0, s1)
        best_k, best_d = -1, -1.0
        for k in range(i + 1, j):
            p0, p1 = pts[k][0] - a0, pts[k][1] - a1
            d = math.hypot(p0, p1) if seg_len == 0 else abs(s1 * p0 - s0 * p1) / seg_len
            if d > best_d:
                best_k, best_d = k, d
        if best_d > tol:
            keep[best_k] = True
            stack.append((i, best_k))
            stack.append((best_k, j))
    return [p for p, k in zip(pts, keep) if k]


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
