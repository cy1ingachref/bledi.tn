"""Expected boarding wait from a line's published departures."""
from __future__ import annotations

from bledi_transit.domain.tunables import (
    DEFAULT_WAIT_BY_MODE,
    MAX_HEADWAY_SEC,
    WAIT_HEADWAY_FACTOR,
)


def expected_wait(departures: list[str] | None, mode: str) -> float:
    """Expected wait in seconds: half the median headway, else a per-mode default."""
    default = DEFAULT_WAIT_BY_MODE.get(mode, DEFAULT_WAIT_BY_MODE["unknown"])
    if not departures:
        return default
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
        return default
    parsed.sort()
    diffs = [parsed[i + 1] - parsed[i] for i in range(len(parsed) - 1)]
    overnight_gap = 0.0
    if parsed[-1] - parsed[0] > MAX_HEADWAY_SEC:
        overnight_gap = 86400.0 - parsed[-1] + parsed[0]
    headways = sorted(diffs + ([overnight_gap] if overnight_gap > 0 else []))
    # Lower median, so the estimate stays conservative.
    median_headway = headways[(len(headways) - 1) // 2]
    return max(median_headway * WAIT_HEADWAY_FACTOR, 0.0)
