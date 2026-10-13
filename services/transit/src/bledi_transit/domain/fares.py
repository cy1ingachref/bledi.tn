"""Approximate fare model.

Not a fare oracle: objective=cheapest ranks by it, so it must be monotone and
defensible rather than exact. Tunisian fares are a flat ticket per mode
(bus, metro, tram), distance-based for trains and per seat for louage, so the
model is base plus per km with a mode-dependent base.
"""
from __future__ import annotations

from typing import Any, Sequence

from bledi_transit.domain.modes import canonical_mode

FARE_DINARS: dict[str, tuple[float, float]] = {
    #  mode        base DT   DT per km
    "bus":        (0.500,   0.000),
    "tram":       (0.500,   0.000),
    "metro":      (0.600,   0.000),
    "train":      (4.000,   0.090),
    "louaj":      (1.000,   0.150),
    "taxi":       (0.600,   0.520),
    "walk":       (0.000,   0.000),
}


def fare_for_leg(mode: str, distance_m: float) -> float:
    """Estimated fare in dinars for one leg. Unknown modes are priced as a bus."""
    base, per_km = FARE_DINARS.get(canonical_mode(mode), FARE_DINARS["bus"])
    km = max(0.0, float(distance_m)) / 1000.0
    return round(base + per_km * km, 4)


def fare_for_itinerary(legs: Sequence[dict[str, Any]]) -> float:
    """Total estimated fare, charged once per boarded line.

    An itinerary is expanded one step per stop, so charging per leg quoted a
    30-stop train ride at ~122 DT instead of ~7. Consecutive legs on the same
    line merge into one charge; walks and transfers are free.
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
