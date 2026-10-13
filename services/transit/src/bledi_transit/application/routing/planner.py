"""Multi-objective planning: several searches, merged, deduplicated and ranked."""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from bledi_transit.domain.fares import fare_for_itinerary
from bledi_transit.domain.geo import haversine_m
from bledi_transit.domain.modes import USER_MODES, canonical_mode, label_modes_fr, resolve_allowed_modes
from bledi_transit.domain.tunables import (
    FEWEST_TRANSFERS_PENALTY_SEC,
    GEOMETRY_REQUIRED_M,
    MAX_START_WALK_METERS,
    TRANSFER_PENALTY_SEC,
    WALK_SPEED_MS,
)

if TYPE_CHECKING:
    from bledi_transit.application.routing.router import Router

OBJECTIVES: tuple[str, ...] = ("fastest", "cheapest", "fewest_transfers")


def plan(
    router: Router,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    objective: str = "fastest",
    max_transfers: int | None = None,
    max_walk_m: float | None = None,
    max_itineraries: int = 3,
) -> dict[str, Any]:
    """Return distinct, labelled itineraries for a filtered request.

    Several searches restricted to different mode sets, not one search with
    different weights: when one journey dominates on every axis (Tunis to
    Sousse by rail), re-weighting returns three copies of it. The fare is
    only a ranking over the candidates, never a search cost.

    Include/exclude is a hard filter inside edge expansion for every
    strategy, so an excluded mode can never appear in a leg.
    """
    if objective not in OBJECTIVES:
        raise ValueError(
            f"unknown objective {objective!r}; expected one of {list(OBJECTIVES)}"
        )
    try:
        max_itineraries = int(max_itineraries)
    except (TypeError, ValueError):
        max_itineraries = 3
    max_itineraries = max(1, min(8, max_itineraries))
    if max_transfers is not None:
        max_transfers = int(max_transfers)
        if max_transfers < 0:
            raise ValueError("max_transfers must be >= 0")

    query = {
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
        "modes_include": list(include) if include else [],
        "modes_exclude": list(exclude) if exclude else [],
        "objective": objective,
        "max_transfers": max_transfers,
        "max_walk_m": max_walk_m,
        "max_itineraries": max_itineraries,
    }
    user_allowed = resolve_allowed_modes(include, exclude)

    # Walking only: no strategy can match the filter, so the direct walk is the answer.
    if user_allowed is not None and not (user_allowed - {"walk"}):
        return {
            "query": query,
            "itineraries": [_present(_walk_candidate(start_lat, start_lon, end_lat, end_lon), 1, objective)],
            "available_modes": list(USER_MODES),
            "message": None,
        }

    bus_only = frozenset({"bus", "rfr", "tram"})
    rail_only = frozenset({"train", "rail", "metro"})
    metro_only = frozenset({"metro"})
    train_only = frozenset({"train", "rail"})

    # user_allowed is the base of every strategy: "fastest" with allowed=None
    # would return the metro journey the user just excluded.
    strategies: list[tuple[str, float, frozenset[str] | None]] = [
        ("fastest", TRANSFER_PENALTY_SEC, user_allowed),
        ("fewest_transfers", FEWEST_TRANSFERS_PENALTY_SEC, user_allowed),
    ]
    for name, subset in (
        ("bus_preferred", bus_only),
        ("rail_preferred", rail_only),
        ("metro_preferred", metro_only),
        ("train_only", train_only),
    ):
        inter = subset if user_allowed is None else (user_allowed & subset)
        if not inter:
            continue
        strategies.append((name, TRANSFER_PENALTY_SEC, inter))

    candidates: list[dict[str, Any]] = []
    for name, penalty, allowed in strategies:
        raw = router.route(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
            allowed_modes=allowed,
            transfer_penalty_sec=penalty,
            max_walk_m=max_walk_m,
        )
        steps = raw.get("steps") or []
        if not steps or raw.get("mode") == "walk" and len(steps) <= 1:
            # Skip the degenerate pure-straight-line walk unless nothing
            # else was found; it is offered as a last resort below.
            continue
        transfers = count_transfers(steps)
        if max_transfers is not None and transfers > max_transfers:
            continue
        complete, gaps = _geometry_report(steps)
        candidates.append(
            {
                "searched_for": name,
                "raw": raw,
                "steps": steps,
                "signature": _itinerary_signature(raw),
                "duration_s": float(raw.get("duration_min") or 0.0) * 60.0,
                "transfers": transfers,
                "fare_estimate": fare_for_itinerary(steps),
                "modes_used": _modes_used(steps),
                "geometry_complete": complete,
                "gaps": gaps,
            }
        )

    if not candidates and haversine_m(start_lat, start_lon, end_lat, end_lon) <= MAX_START_WALK_METERS * 2:
        candidates.append(_walk_candidate(start_lat, start_lon, end_lat, end_lon))

    if not candidates:
        return {
            "query": query,
            "itineraries": [],
            "available_modes": list(USER_MODES),
            "message": _no_route_message(include, exclude),
        }

    # The secondary key breaks ties so the order is deterministic.
    if objective == "cheapest":
        candidates.sort(key=lambda c: (c["fare_estimate"], c["duration_s"]))
    elif objective == "fewest_transfers":
        candidates.sort(key=lambda c: (c["transfers"], c["duration_s"]))
    else:
        candidates.sort(key=lambda c: (c["duration_s"], c["transfers"]))

    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for c in candidates:
        if c["signature"] in seen:
            continue
        seen.add(c["signature"])
        out.append(c)
        if len(out) >= max_itineraries:
            break

    return {
        "query": query,
        "itineraries": [_present(c, i + 1, objective) for i, c in enumerate(out)],
        "available_modes": list(USER_MODES),
        "message": None,
    }


def count_transfers(steps: Sequence[dict[str, Any]]) -> int:
    lines = [
        s.get("line") or "" for s in (steps or ()) if s.get("type") == "ride"
    ]
    changes = 0
    for i in range(1, len(lines)):
        if lines[i] != lines[i - 1]:
            changes += 1
    return changes


def _walk_candidate(start_lat: float, start_lon: float, end_lat: float, end_lon: float) -> dict[str, Any]:
    direct_m = haversine_m(start_lat, start_lon, end_lat, end_lon)
    walk_s = direct_m / WALK_SPEED_MS
    steps = [
        {
            "type": "walk",
            "from": {"lat": start_lat, "lon": start_lon},
            "to": {"lat": end_lat, "lon": end_lon},
            "distance_m": round(direct_m),
            "duration_min": round(walk_s / 60, 1),
            "time_seconds": round(walk_s, 1),
            "label": f"Marcher {round(direct_m)} m (~{round(walk_s / 60)} min)",
        }
    ]
    return {
        "searched_for": "walk",
        "raw": {"mode": "walk", "duration_min": round(walk_s / 60, 1), "steps": steps},
        "steps": steps,
        "signature": _itinerary_signature({"steps": steps}),
        "duration_s": walk_s,
        "transfers": 0,
        "fare_estimate": 0.0,
        "modes_used": ["walk"],
        "geometry_complete": False,
        "gaps": [],
    }


def _itinerary_signature(result: dict[str, Any]) -> tuple:
    """Distinctness key: the ordered (mode, line_id) of every ride leg.

    Walks are excluded: two itineraries that differ only in how far the
    rider walks to the same bus are one choice for the rider.
    """
    sig: list[tuple[str, str]] = []
    for step in result.get("steps") or ():
        if step.get("type") != "ride":
            continue
        entry = (step.get("mode") or "", step.get("line") or "")
        # Steps are per stop, so one ride on a line is several equal entries.
        if sig and sig[-1] == entry:
            continue
        sig.append(entry)
    if not sig:
        # No rides at all (pure walk / pure taxi): fall back on mode+shape.
        sig = [
            (step.get("type") or "", "")
            for step in result.get("steps") or ()
            if step.get("type") in ("taxi", "walk")
        ]
    return tuple(sig)


def _modes_used(steps: Sequence[dict[str, Any]]) -> list[str]:
    used: set[str] = set()
    for step in steps or ():
        if step.get("type") in ("walk", "transfer"):
            continue
        m = canonical_mode(step.get("mode") or step.get("type") or "")
        if m != "walk":
            used.add(m)
    return [m for m in USER_MODES if m in used]


def _geometry_report(steps: Sequence[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    """(geometry_complete, gaps): a gap is a leg long enough to need a
    polyline that has none, which the client must not draw as a straight line.
    """
    gaps: list[dict[str, Any]] = []
    for step in steps or ():
        dist = float(step.get("distance_m") or 0.0)
        if step.get("geometry") or dist < GEOMETRY_REQUIRED_M:
            continue
        gaps.append(
            {
                "type": step.get("type"),
                "mode": step.get("mode"),
                "line": step.get("line"),
                "from": step.get("from"),
                "to": step.get("to"),
                "distance_m": round(dist),
                "straight_m": step.get("straight_m"),
                "reason": "no_cached_geometry",
            }
        )
    return (not gaps), gaps


def _present(c: dict[str, Any], n: int, objective: str) -> dict[str, Any]:
    raw = c["raw"]
    modes = c["modes_used"]
    duration_min = round(c["duration_s"] / 60.0, 1)
    tr = c["transfers"]
    bits = [label_modes_fr(modes) or "Marche"]
    bits.append(_fmt_dur_fr(duration_min))
    if tr:
        bits.append(f"{tr} correspondance{'s' if tr > 1 else ''}")
    else:
        bits.append("direct")
    return {
        "id": f"opt_{n}",
        "label": " · ".join(bits),
        "rank_reason": _rank_reason_fr(c, objective, n),
        "mode": raw.get("mode"),
        "duration_min": duration_min,
        "duration_s": round(c["duration_s"], 1),
        "transfers": tr,
        "fare_estimate_dinars": c["fare_estimate"],
        "modes_used": modes,
        "legs": c["steps"],
        "steps": c["steps"],
        "geometry_complete": c["geometry_complete"],
        "gaps": c["gaps"],
        "searched_for": c["searched_for"],
    }


def _fmt_dur_fr(minutes: float) -> str:
    m = int(round(minutes))
    if m < 60:
        return f"{m} min"
    h, rem = divmod(m, 60)
    return f"{h} h {rem:02d}" if rem else f"{h} h"


def _rank_reason_fr(c: dict[str, Any], objective: str, n: int) -> str:
    modes = label_modes_fr(c["modes_used"]) or "Marche"
    tr = c["transfers"]
    dur = _fmt_dur_fr(c["duration_s"] / 60.0)
    if n == 1:
        if objective == "cheapest":
            return f"le moins cher · {c['fare_estimate']:.2f} DT · {dur}"
        if objective == "fewest_transfers":
            return f"le moins de correspondances · {tr} · {dur}"
        return f"le plus rapide · {dur}"
    return f"{modes} · {dur} · {tr} correspondance{'s' if tr > 1 else ''}"


def _no_route_message(
    include: Sequence[str] | None,
    exclude: Sequence[str] | None,
) -> str:
    """Actionable French message when filters leave no journey."""
    if exclude:
        return (
            "Aucun itineraire avec les modes selectionnes; essayez d'activer "
            + ", ".join(sorted(set(USER_MODES) - {canonical_mode(m) for m in exclude}))
            + "."
        )
    if include:
        return (
            "Aucun itineraire pour ces modes; essayez d'en ajouter un autre "
            f"({', '.join(USER_MODES)})."
        )
    return "Aucun itineraire trouve entre ces deux points."
