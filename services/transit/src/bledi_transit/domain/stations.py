"""Rider-facing modes of a station row.

The seed keeps raw provenance tags in `mode` (rail, louage_red, unknown...).
They are not selectable modes: the UI filter and the map palette key off the
canonical vocabulary. `unknown` marks 76 stops whose operator export carried
no mode at all (kiosks, roundabouts, school stops); they stay on the map as
`unclassified`, never as a scheduled bus.
"""
from __future__ import annotations

from typing import Any

from bledi_transit.domain.modes import USER_MODES, canonical_mode

UNCLASSIFIED = "unclassified"

_UNCLASSIFIED_TAGS = frozenset({"unknown", "unclassified", ""})


def station_modes(s: dict[str, Any]) -> list[str]:
    """Canonical modes a station serves, in USER_MODES order, unclassified last.

    A stop tagged `rail` yields ["train"], `louage_red` yields ["louaj"], an
    untagged sweep stop yields ["unclassified"].
    """
    raw: list[str] = []
    primary = s.get("mode")
    if primary:
        raw.append(str(primary))
    for extra in s.get("modes") or []:
        if extra:
            raw.append(str(extra))

    seen: set[str] = set()
    for r in raw:
        rl = r.strip().lower()
        if not rl:
            continue
        seen.add(UNCLASSIFIED if rl in _UNCLASSIFIED_TAGS else canonical_mode(rl))

    ordered = [m for m in USER_MODES if m in seen]
    if UNCLASSIFIED in seen:
        ordered.append(UNCLASSIFIED)
    return ordered


def primary_station_mode(s: dict[str, Any]) -> str:
    """The mode used to colour a station dot; a routable mode wins over unclassified."""
    modes = station_modes(s)
    for m in modes:
        if m != UNCLASSIFIED:
            return m
    return modes[0] if modes else UNCLASSIFIED
