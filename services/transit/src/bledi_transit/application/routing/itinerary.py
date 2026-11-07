"""Turn a searched path (stations + lines arrived on) into timed, drawable steps."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bledi_transit.application.routing.graph import transit_speed_kmh
from bledi_transit.application.routing.legs import resolve_walk_geometry
from bledi_transit.domain.cities import nearest_city
from bledi_transit.domain.geo import haversine_m
from bledi_transit.domain.modes import TAXI_MODES
from bledi_transit.domain.tunables import (
    GEOMETRY_REQUIRED_M,
    MAX_END_WALK_METERS,
    TAXI_SPEED_KMH,
    TRANSFER_PENALTY_SEC,
    WALK_SPEED_KMH,
)

if TYPE_CHECKING:
    from bledi_transit.application.routing.router import Router


def expand_path(
    router: Router,
    path_stations: list[str],
    path_lines: list[str | None],
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    s_start: dict[str, Any] | None,
    s_end: dict[str, Any] | None,
    allowed_modes: frozenset[str] | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    """Convert a search path into timed steps.

    The start walk is already accounted for in the search's initial label, so
    this only adds the transit/transfer segments and the end walk.
    """
    paths = router.paths
    steps: list[dict[str, Any]] = []
    total_min = 0.0

    first = router.stations.get(path_stations[0]) if path_stations else None
    if first and first.get("lat") and first.get("lon"):
        prev_lat, prev_lon = first["lat"], first["lon"]
        prev_name = first.get("name", "")
    else:
        prev_lat, prev_lon = start_lat, start_lon
        prev_name = "Départ"

    if s_start and first and first.get("lat") and first.get("lon"):
        straight_walk_m = haversine_m(start_lat, start_lon, first["lat"], first["lon"])
        # The straight line stays the distance floor, so a graph miss costs
        # the polyline but never a shorter-than-possible walk.
        live = paths.road(start_lat, start_lon, first["lat"], first["lon"], "foot")
        walk_m = straight_walk_m
        walk_geom: list[list[float]] = []
        if live is not None and live[1] >= 0.95 * straight_walk_m:
            walk_geom, walk_m = live[0], live[1]
        if walk_m > 1:
            walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
            steps.append({
                "type": "walk",
                "from": {"lat": start_lat, "lon": start_lon},
                "to": {"lat": first["lat"], "lon": first["lon"]},
                "geometry": walk_geom,
                "straight_m": round(straight_walk_m),
                # Without it the map labels the first milestone with the
                # whole instruction instead of the station name.
                "to_name": first.get("name", ""),
                "distance_m": round(walk_m),
                "duration_min": round(walk_min, 1),
                "time_seconds": round(walk_min * 60, 1),
                "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'à {first.get('name', '')}",
            })
            total_min += walk_min

    for i in range(len(path_stations) - 1):
        a_id = path_stations[i]
        b_id = path_stations[i + 1]
        a = router.stations.get(a_id)
        b = router.stations.get(b_id)
        if not a or not b or not a.get("lat") or not a.get("lon") or not b.get("lat") or not b.get("lon"):
            continue
        line_used = path_lines[i + 1]  # line arrived on at b = line used for a->b
        straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        # The traversed edge, so the reported step equals the optimised cost.
        edge = router.edge_between(a_id, b_id, line_used)
        seg_m = edge.distance_m if edge else straight_m
        seg_geom = edge.geometry if edge else []

        if line_used is None and seg_m > 1:
            # Walk edges are built without live routing (see add_walk_edges),
            # so the real path is resolved only for walks on the itinerary.
            wg, seg_m = resolve_walk_geometry(
                paths, a["lat"], a["lon"], b["lat"], b["lon"], seg_geom or None
            )
            seg_geom = wg
            walk_min = seg_m / 1000 / WALK_SPEED_KMH * 60
            steps.append({
                "type": "walk",
                "from": {"lat": a["lat"], "lon": a["lon"]},
                "to": {"lat": b["lat"], "lon": b["lon"]},
                "from_name": a.get("name", ""),
                "to_name": b.get("name", ""),
                "from_id": a_id,
                "to_id": b_id,
                "mode": "walk",
                "distance_m": round(seg_m),
                "duration_min": round(walk_min, 1),
                "time_seconds": round(walk_min * 60, 1),
                "geometry": seg_geom,
                "label": f"Marcher {round(seg_m)} m jusqu'à {b.get('name', '')}",
            })
            total_min += walk_min
            prev_lat, prev_lon = b["lat"], b["lon"]
            prev_name = b.get("name", "")
            continue

        # No line and no distance: the same point twice on the path (stops
        # sharing a coordinate, or a zero-length walk). Nothing to show.
        if line_used is None:
            continue

        mode = router.user_mode_of_line.get(line_used or "", "bus") or "bus"
        # Real track first: the cache covers only 1 776 of ~3 900 station
        # pairs and its gaps are almost all rail. The cache stays the fallback
        # when the points are not on one connected track.
        if mode in ("train", "metro", "tram"):
            live_rail = paths.rail(a["lat"], a["lon"], b["lat"], b["lon"])
            if live_rail is not None and live_rail[1] >= 0.95 * straight_m:
                seg_geom = live_rail[0]
                seg_m = live_rail[1]
                edge = None  # force re-timing from the real track distance

        # The raw seed mode, not the canonical one: canonical_mode() folds
        # "rail" into "train", which SPEED_BY_MODE times differently.
        raw_mode = router.mode_of_line.get(line_used or "", "bus") or "bus"
        # Live road first for road modes: the cached geometry may be from an
        # older seed or missing, but the live graph is the drawn line. When
        # live road exists, distance must follow it, not the cached straight
        # line. The old "if not seg_geom" guard kept the cached distance
        # while drawing the live geometry, making the reported distance
        # disagree with the drawn line.
        if mode in ("bus", "louaj", "taxi", "rural") and straight_m >= GEOMETRY_REQUIRED_M:
            live_road = paths.road(a["lat"], a["lon"], b["lat"], b["lon"], "car")
            if live_road is not None and live_road[1] >= 0.95 * straight_m:
                seg_geom = live_road[0]
                seg_m = live_road[1]
                edge = None  # force re-timing from the real road distance
        ride_m = seg_m
        ride_min = (
            (edge.time_s / 60.0)
            if edge
            else (ride_m / 1000 / transit_speed_kmh(raw_mode, ride_m) * 60)
        )

        prev_line = path_lines[i]  # line arrived on at a
        # The search cost already includes the boarding wait; adding it here
        # keeps the displayed duration equal to it.
        boarding = (prev_line is None or prev_line != line_used)
        wait_min = 0.0
        transfer_min = 0.0
        if boarding:
            wait_min = router.line_wait.get(line_used or "", 0.0) / 60.0
            if prev_line is not None:
                transfer_min = TRANSFER_PENALTY_SEC / 60.0

        if transfer_min > 0:
            steps.append({
                "type": "transfer",
                "from": {"lat": prev_lat, "lon": prev_lon},
                "to": {"lat": a["lat"], "lon": a["lon"]},
                "to_name": a.get("name", ""),
                "mode": "transfer",
                "distance_m": 0,
                "time_seconds": round(transfer_min * 60, 1),
                "duration_min": round(transfer_min, 1),
                "label": f"Correspondance : marcher jusqu'a {a.get('name', '')}",
            })
            total_min += transfer_min

        display_ride_min = ride_min + wait_min
        wait_label = ""
        if wait_min > 0:
            wait_label = " (~" + str(round(wait_min)) + " min d'attente)"
        steps.append({
            "type": "ride",
            "line": line_used or "",
            "mode": mode,
            "from": {"lat": a["lat"], "lon": a["lon"]},
            "to": {"lat": b["lat"], "lon": b["lon"]},
            "from_name": a.get("name", ""),
            "to_name": b.get("name", ""),
            # The /route/transit envelope looks up the cached track by station pair.
            "from_id": a_id,
            "to_id": b_id,
            "distance_m": round(ride_m),
            "duration_min": round(display_ride_min, 1),
            "wait_min": round(wait_min, 1),
            "time_seconds": round(display_ride_min * 60, 1),
            "geometry": seg_geom,
            "straight_m": round(straight_m),
            # The client refuses to draw a straight line across open country.
            "needs_geometry": bool(
                not seg_geom and straight_m >= GEOMETRY_REQUIRED_M
            ),
            "label": f"{mode} — {a.get('name', '')} → {b.get('name', '')}{wait_label}",
        })
        total_min += display_ride_min
        prev_lat, prev_lon = b["lat"], b["lon"]
        prev_name = b.get("name", "")

    if s_end and s_end.get("lat") and s_end.get("lon"):
        straight_walk_m = haversine_m(prev_lat, prev_lon, end_lat, end_lon)
        # A gap past MAX_END_WALK_METERS is a taxi hop; on the foot network
        # it would go down footpaths and stairs.
        leg_mode = "foot" if straight_walk_m <= MAX_END_WALK_METERS else "car"
        live = paths.road(prev_lat, prev_lon, end_lat, end_lon, leg_mode)
        walk_m = straight_walk_m
        walk_geom = []
        if live is not None and live[1] >= 0.95 * straight_walk_m:
            walk_geom, walk_m = live[0], live[1]
        if walk_m > 1:
            # Distance decides, as in the cost branch of route(), so the drawn
            # leg and the cost agree. A taxi hop also needs a taxi mode
            # selected: "bus only" must not return a bus and taxi itinerary.
            hop_permitted = allowed_modes is None or bool(allowed_modes & TAXI_MODES)
            from bledi_transit.domain.cities import UNASSIGNED_CITY

            def _crosses(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> bool:
                ca, cb = nearest_city(a_lat, a_lon), nearest_city(b_lat, b_lon)
                return ca != cb and ca != UNASSIGNED_CITY and cb != UNASSIGNED_CITY

            # A gap taxi hop must not cross governorates either (same rule as
            # the direct taxi gate in router.py). Cross-gov gaps are walk.
            gap_city_ok = not _crosses(prev_lat, prev_lon, end_lat, end_lon)
            if walk_m > MAX_END_WALK_METERS and hop_permitted and gap_city_ok:
                hop_min = walk_m / 1000 / TAXI_SPEED_KMH * 60
                steps.append({
                    "type": "taxi",
                    "from": {"lat": prev_lat, "lon": prev_lon},
                    "to": {"lat": end_lat, "lon": end_lon},
                    "from_name": prev_name,
                    "geometry": walk_geom,
                    "straight_m": round(straight_walk_m),
                    "distance_m": round(walk_m),
                    "distance_km": round(walk_m / 1000, 1),
                    "duration_min": round(hop_min, 1),
                    "time_seconds": round(hop_min * 60, 1),
                    "note": "no_stop_near_destination",
                    "label": (
                        f"Taxi local ~{round(walk_m / 1000, 1)} km jusqu'a destination "
                        f"(aucun arret de transport a proximite)"
                    ),
                })
                total_min += hop_min
            else:
                walk_min = walk_m / 1000 / WALK_SPEED_KMH * 60
                steps.append({
                    "type": "walk",
                    "from": {"lat": prev_lat, "lon": prev_lon},
                    "to": {"lat": end_lat, "lon": end_lon},
                    "geometry": walk_geom,
                    "straight_m": round(straight_walk_m),
                    "distance_m": round(walk_m),
                    "duration_min": round(walk_min, 1),
                    "time_seconds": round(walk_min * 60, 1),
                    "label": f"Marcher {round(walk_m)} m (~{round(walk_min)} min) jusqu'a destination",
                })
                total_min += walk_min

    return round(total_min, 1), steps
