"""Louage and rural-transport corridors: designated lines with boardable stops.

A louage does not go from anywhere to anywhere. It runs on one corridor between two stands
(e.g. Tunis Bab Saadoun to Mateur) and picks up and drops at the towns it passes (Djedeida), so
a rider from Tebourba reaches Mateur by getting to Djedeida first and boarding there. Rural
transport ("naqel rifi") works the same way over short hops (Tebourba to Edkhila, then Edkhila
to Mateur). That is exactly a line with an ordered list of stops, so a corridor is converted
into a normal line and the router needs no special case: the rider may board and alight at any
listed stop, in both directions, and transfers happen wherever two stops are within walking
distance.

File: data/louage_corridors.json (optional)

    {
      "stops": [ {"id": "louage_djedeida", "name": "Djedeida (louage)", "lat": 36.85, "lon": 9.93} ],
      "corridors": [
        {"id": "louage_bab_saadoun_mateur", "number": "L31", "mode": "louage",
         "name": "Tunis - Bab Saadoun -> Mateur (via Djedeida)",
         "stops": ["louage_tunis_bab_saadoun", "louage_djedeida", "<id of the Mateur stand>"],
         "wait_min": 15, "verified": true}
      ]
    }

`stops` entries are station ids: either already in the seed or defined in the top-level "stops".
Only corridors marked "verified": true are loaded, unless BLEDI_LOUAGE_UNVERIFIED=1 (for
trying a draft); nothing unconfirmed reaches riders by accident.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("bledi.corridors")

CORRIDORS_FILE = "louage_corridors.json"
TUNISIA_BBOX = (30.0, 37.7, 7.0, 11.8)  # lat min, lat max, lon min, lon max
MODES = ("louage", "bus", "rural")  # bus = scheduled/rural shuttles; rural = nakel rifi corridors


@dataclass
class CorridorReport:
    loaded: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (corridor id, reason)
    stops_added: list[str] = field(default_factory=list)


def _in_tunisia(lat: Any, lon: Any) -> bool:
    return (
        isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        and TUNISIA_BBOX[0] <= lat <= TUNISIA_BBOX[1] and TUNISIA_BBOX[2] <= lon <= TUNISIA_BBOX[3]
    )


def merge_corridors(
    data: dict[str, Any],
    stations: list[dict[str, Any]],
    lines: list[dict[str, Any]],
    *,
    include_unverified: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], CorridorReport]:
    """Return (stations, lines, report) with the valid corridors added. Inputs are not mutated."""
    report = CorridorReport()
    known = {s["id"] for s in stations if s.get("id")}
    existing_lines = {ln.get("id") for ln in lines}

    inline: dict[str, dict[str, Any]] = {}
    for raw in data.get("stops") or []:
        sid = raw.get("id")
        if not sid or sid in known or sid in inline:
            report.skipped.append((str(sid), "stop id missing or already exists"))
            continue
        if not _in_tunisia(raw.get("lat"), raw.get("lon")) or not raw.get("name"):
            report.skipped.append((str(sid), "stop needs a name and coordinates inside Tunisia"))
            continue
        inline[sid] = {
            "id": sid, "name": raw["name"], "lat": float(raw["lat"]), "lon": float(raw["lon"]),
            "mode": raw.get("mode", "louage"), "source": CORRIDORS_FILE,
            **({"name_ar": raw["name_ar"]} if raw.get("name_ar") else {}),
        }

    new_lines: list[dict[str, Any]] = []
    used_inline: set[str] = set()
    for c in data.get("corridors") or []:
        cid = str(c.get("id") or "")
        if not cid:
            report.skipped.append(("?", "corridor has no id"))
            continue
        if not (c.get("verified") is True or include_unverified):
            report.skipped.append((cid, "unverified"))
            continue
        mode = c.get("mode", "louage")
        if mode not in MODES:
            report.skipped.append((cid, f"mode must be one of {MODES}"))
            continue
        stops: list[str] = []
        for sid in c.get("stops") or []:
            if not stops or stops[-1] != sid:  # collapse accidental repeats
                stops.append(sid)
        missing = [s for s in stops if s not in known and s not in inline]
        if len(stops) < 2:
            report.skipped.append((cid, "needs at least 2 stops"))
            continue
        if missing:
            report.skipped.append((cid, f"unknown stop ids: {missing}"))
            continue
        line_id = cid if cid.startswith("corridor_") else f"corridor_{cid}"
        if line_id in existing_lines or any(ln["id"] == line_id for ln in new_lines):
            report.skipped.append((cid, "duplicate corridor id"))
            continue
        used_inline.update(s for s in stops if s in inline)
        line: dict[str, Any] = {
            "id": line_id,
            "number": str(c.get("number") or cid),
            "name": c.get("name") or cid,
            "operator": c.get("operator") or ("louage" if mode == "louage" else "Transport rural"),
            "mode": mode,
            "type": "corridor",
            "route_id": cid,
            "stations": stops,
            "departures": c.get("departures") or [],
            "source": CORRIDORS_FILE,
            "license_status": "user-supplied",
        }
        if c.get("wait_min") is not None:
            line["wait_s"] = float(c["wait_min"]) * 60.0
        new_lines.append(line)
        report.loaded.append(cid)

    added = [inline[s] for s in inline if s in used_inline]
    report.stops_added = [s["id"] for s in added]
    return [*stations, *added], [*lines, *new_lines], report
