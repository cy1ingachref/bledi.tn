"""Per-mode defaults for derived wait/speed/fare values.

These are ESTIMATES used only when a source (operator schedule, official fare
table, real OSM data) does not provide the value. Every derived value is marked
`estimated: true` with its source so the API and UI can flag it.

Official data overrides: a line with an explicit `wait_s`, `speed_kmh` or
`fare_dinars` in the seed wins over these defaults. The Tebourba schedule PDF
lines are the known official-public override case; they carry their own values
in the legacy seed and are therefore not estimated.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeDefault:
    headway_s: float
    speed_kmh: float
    fare_dinars: float
    source: str
    estimated: bool = True


# Conservative, documented defaults. Speeds/fares mirror the existing tunables
# so introducing this config does not change routing cost; it only makes the
# provenance of those numbers explicit.
MODE_DEFAULTS: dict[str, ModeDefault] = {
    "bus":    ModeDefault(600.0, 22.0, 0.50, "estimate: urban Tunisian bus (flat ticket)"),
    "tram":   ModeDefault(600.0, 22.0, 0.50, "estimate: tram (flat ticket)"),
    "metro":  ModeDefault(300.0, 30.0, 0.60, "estimate: Tunis metro (flat ticket)"),
    "train":  ModeDefault(600.0, 60.0, 4.00, "estimate: SNCFT intercity base + per km"),
    "rail":   ModeDefault(600.0, 55.0, 4.00, "estimate: SNCFT regional base + per km"),
    "louage": ModeDefault(600.0, 100.0, 1.00, "estimate: shared intercity van base + per km"),
    "louaj":  ModeDefault(600.0, 100.0, 1.00, "estimate: shared intercity van base + per km"),
    "taxi":   ModeDefault(0.0, 45.0, 0.60, "estimate: taxi base + per km"),
    "rural":  ModeDefault(600.0, 22.0, 0.50, "estimate: rural bus as urban bus"),
    "rfr":    ModeDefault(600.0, 22.0, 0.50, "estimate: regional rail feeder as bus"),
    "walk":   ModeDefault(0.0, 4.5, 0.00, "walking speed constant"),
    "unknown": ModeDefault(600.0, 22.0, 0.50, "estimate: unknown mode priced as bus"),
}


def defaults_for(mode: str) -> ModeDefault:
    return MODE_DEFAULTS.get(mode, MODE_DEFAULTS["unknown"])


def as_dict(mode: str) -> dict:
    d = defaults_for(mode)
    return {
        "headway_s": d.headway_s, "speed_kmh": d.speed_kmh,
        "fare_dinars": d.fare_dinars, "source": d.source,
        "estimated": d.estimated,
    }
