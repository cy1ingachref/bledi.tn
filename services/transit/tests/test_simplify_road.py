"""The road simplifier must keep the line within tolerance of the real road."""
from __future__ import annotations

import math

from bledi_transit.adapters.graphs.road_graph import _simplify
from bledi_transit.domain.geo import haversine_m


def _arc(radius_m=30_000.0, length_m=100_000.0, step_m=25.0):
    lat0, lon0 = 36.0, 10.0
    out = []
    for i in range(int(length_m / step_m)):
        th = i * step_m / radius_m
        x, y = radius_m * math.sin(th), radius_m * (1 - math.cos(th))
        out.append([lat0 + y / 111_320.0, lon0 + x / (111_320.0 * math.cos(math.radians(lat0)))])
    return out


def _max_dev_m(simplified, original):
    k = 111_320.0
    worst = 0.0
    for p in original[::20]:
        c = math.cos(math.radians(p[0]))
        best = float("inf")
        for a, b in zip(simplified, simplified[1:]):
            ax, ay = (a[1] - p[1]) * k * c, (a[0] - p[0]) * k
            bx, by = (b[1] - p[1]) * k * c, (b[0] - p[0]) * k
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy
            t = 0.0 if ll == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / ll))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
        worst = max(worst, best)
    return worst


def test_gentle_curve_is_not_collapsed_into_a_chord():
    pts = _arc()
    s = _simplify(pts)
    assert len(s) > 20
    assert max(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(s, s[1:])) < 5_000
    assert _max_dev_m(s, pts) <= 8.5


def test_endpoints_and_short_inputs_are_kept():
    pts = _arc(length_m=500)
    s = _simplify(pts)
    assert s[0] == pts[0] and s[-1] == pts[-1]
    assert _simplify(pts[:2]) == pts[:2]
