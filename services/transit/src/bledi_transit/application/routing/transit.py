"""The /route/transit envelope: one itinerary in the best_fastest / legs shape the clients draw."""
from __future__ import annotations

from typing import Any, Callable

from bledi_transit.domain.geo import haversine_m

SegmentGeometry = Callable[[str | None, str | None], list[list[float]]]

_MODE_COLORS = {"metro": "#339af0", "train": "#845ef7", "rfr": "#ff922b", "bus": "#e03131"}


def _mode_color(mode: str) -> str:
    return _MODE_COLORS.get(mode, "#8b949e")


def _leg_from_step(step: dict[str, Any], gap_breaks: bool = False) -> dict[str, Any]:
    """One leg from one step.

    A leg with no real path is marked `needs_geometry`; the map must draw
    nothing, or an explicit unverified placeholder, rather than a straight line
    across open country. `geometry_gap_m` says how far that omission spans.
    `gap_breaks` records that this leg is a hole in an otherwise continuous ride.
    """
    geom = step.get("geometry") or []
    frm, to = step.get("start"), step.get("end")
    gap_m = None
    if len(geom) < 2 and frm and to:
        gap_m = round(haversine_m(frm[0], frm[1], to[0], to[1]))
    return {
        "mode": step.get("mode"),
        "type": step.get("type"),
        "line": step.get("line"),
        "from": frm,
        "to": to,
        "from_name": step.get("from_name"),
        "to_name": step.get("to_name"),
        "from_id": step.get("from_id"),
        "to_id": step.get("to_id"),
        "geometry": geom,
        "has_geometry": len(geom) >= 2,
        "geometry_missing": len(geom) < 2,
        "needs_geometry": bool(step.get("needs_geometry")) and len(geom) < 2,
        "geometry_gap_m": gap_m,
        "breaks_continuity": gap_breaks,
        "distance_m": step.get("distance_m"),
        "straight_m": step.get("straight_m"),
        "time_seconds": step.get("time_seconds"),
        "duration": step.get("time_seconds"),
    }


def steps_to_legs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One leg per movement, consecutive rides on the same line merged.

    A sub-step with no polyline breaks the merge and becomes its own flagged
    leg. Stitching over it would draw one line jumping across open country,
    such as the 125 km Borj Cedria to Sidi Bou Goubrine stretch with no rail
    geometry in the seed.
    """
    legs: list[dict[str, Any]] = []
    for s in steps:
        kind = s.get("type")
        mode = s.get("mode") or ("walk" if kind == "walk" else kind)
        line = s.get("line")
        geom = s.get("geometry") or []
        prev = legs[-1] if legs else None
        mergeable = (
            kind == "ride"
            and prev is not None
            and prev.get("type") == "ride"
            and prev.get("mode") == mode
            and (prev.get("line") or None) == (line or None)
        )
        # The hole can be the step being appended OR the leg already
        # accumulated: the first step of a ride may itself be the unmatchable one.
        prev_has_hole = bool(mergeable and prev.get("needs_geometry"))
        if mergeable and (prev_has_hole or (not geom and s.get("needs_geometry"))):
            legs.append(_leg_from_step(s, gap_breaks=prev_has_hole))
            continue
        if mergeable:
            if geom:
                prev["geometry"] = (prev.get("geometry") or []) + geom
            if s.get("to_id"):
                prev["to_id"] = s.get("to_id")
            prev["to"] = s.get("end")
            prev["to_name"] = s.get("to_name")
            # The merged leg's endpoints and polyline differ from the first
            # step it absorbed, so its geometry flags are re-derived.
            prev["has_geometry"] = len(prev.get("geometry") or []) >= 2
            prev["geometry_missing"] = not prev["has_geometry"]
            prev["needs_geometry"] = False
            prev["geometry_gap_m"] = (
                None
                if prev["has_geometry"] or not (prev.get("from") and prev.get("to"))
                else round(haversine_m(prev["from"][0], prev["from"][1], prev["to"][0], prev["to"][1]))
            )
            prev["distance_m"] = round((prev.get("distance_m") or 0) + (s.get("distance_m") or 0))
            prev["time_seconds"] = round((prev.get("time_seconds") or 0) + (s.get("time_seconds") or 0), 1)
            continue
        legs.append(_leg_from_step(s))
    return legs


def _point(p: Any) -> tuple[float, float]:
    if isinstance(p, dict):
        return p.get("lat"), p.get("lon")
    if isinstance(p, list):
        return p[0], p[1]
    return 0.0, 0.0


def router_to_option(router_out: dict[str, Any], segment_geometry: SegmentGeometry) -> dict[str, Any]:
    """A Router.route() result in the best_fastest option shape."""
    if router_out.get("mode") == "walk":
        return {
            "duration": round(router_out.get("duration_min", 0) * 60, 1),
            "duration_min": router_out.get("duration_min", 0),
            "transfers": 0,
            "has_walk_transfer": True,
            "steps": [
                {
                    "type": "walk",
                    "start": [s["from"]["lat"], s["from"]["lon"]],
                    "end": [s["to"]["lat"], s["to"]["lon"]],
                    "color": "#8E8E93",
                    "stop_name": s.get("label", ""),
                    "to_name": s.get("to_name"),
                    "from_name": s.get("from_name"),
                    "geometry": [],
                    "has_geometry": False,
                    "mode": "walk",
                    "line": None,
                }
                for s in router_out.get("steps", [])
            ],
        }

    dur_min = router_out.get("duration_min", 0)
    steps_raw = router_out.get("steps", [])
    # Any walk between the access and the egress walk is a walking transfer.
    has_walk_transfer = any(ss.get("type") == "walk" for ss in steps_raw[1:-1])
    steps_out: list[dict[str, Any]] = []
    transfer_count = 0
    prev_mode: str | None = None
    after_transfer = False
    for s in steps_raw:
        t = s.get("type", "ride")
        line = s.get("line") or ""
        st_mode = s.get("mode", "bus") if t == "ride" else t
        fr_lat, fr_lon = _point(s.get("from", {}))
        to_lat, to_lon = _point(s.get("to", {}))
        # A bus -> train change emits a transfer step AND a mode change on the
        # next ride; count it once.
        if t == "transfer":
            transfer_count += 1
            after_transfer = True
        elif t == "ride" and prev_mode is not None and prev_mode != st_mode:
            if not after_transfer:
                transfer_count += 1
            after_transfer = False
        if t != "transfer":
            after_transfer = False
        geom: list[list[float]] = s.get("geometry") or []
        if not geom and t == "ride" and not s.get("needs_geometry"):
            # A flagged leg has no real path; filling it from the station pair
            # cache would report the false line the flag exists to prevent.
            geom = segment_geometry(s.get("from_id"), s.get("to_id"))
        steps_out.append(
            {
                "type": t,
                "start": [fr_lat, fr_lon],
                "end": [to_lat, to_lon],
                "color": _mode_color(st_mode if t == "ride" else "walk"),
                "stop_name": (s.get("to_name") or s.get("label") or "").strip(),
                # stop_name falls back to the instruction text for walk and
                # taxi legs, so the station names travel separately.
                "to_name": s.get("to_name"),
                "from_name": s.get("from_name"),
                "mode": st_mode,
                "line": line if t == "ride" else None,
                "geometry": geom,
                "has_geometry": len(geom) >= 2,
                "distance_m": s.get("distance_m"),
                "time_seconds": s.get("time_seconds"),
                "from_id": s.get("from_id"),
                "to_id": s.get("to_id"),
                "straight_m": s.get("straight_m"),
                "needs_geometry": s.get("needs_geometry", False),
            }
        )
        prev_mode = st_mode if t == "ride" else prev_mode

    return {
        "duration": round(dur_min * 60, 1),
        "duration_min": dur_min,
        "transfers": transfer_count,
        "has_walk_transfer": has_walk_transfer,
        "steps": steps_out,
        "fare_dinars": router_out.get("fare_dinars"),
    }


def transit_itinerary(router_out: dict[str, Any], segment_geometry: SegmentGeometry) -> dict[str, Any]:
    if router_out.get("error"):
        return {"error": router_out["error"], "source": "local-router"}
    option = router_to_option(router_out, segment_geometry)
    if not option.get("steps"):
        return {"error": "No transit route found", "source": "local-router"}
    return {
        "best_fastest": option,
        "best_less_walk": None,
        "alternatives": [],
        # `steps` above stays byte-identical for the existing renderers; this is
        # the one-entry-per-movement view of the same itinerary.
        "legs": steps_to_legs(option.get("steps", [])),
        "source": "local-router",
    }
