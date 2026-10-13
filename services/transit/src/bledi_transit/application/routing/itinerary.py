"""Turn a searched path (stations + lines arrived on) into timed, drawable steps."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bledi_transit.application.routing.graph import transit_speed_kmh
from bledi_transit.application.routing.legs import resolve_walk_geometry
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

    # Start walk (only if the search source station differs from the actual
    # start point, i.e. the walk was non-zero).
    if s_start and first and first.get("lat") and first.get("lon"):
        straight_walk_m = haversine_m(start_lat, start_lon, first["lat"], first["lon"])
        # Real pedestrian route when the road graph can serve the pair. The
        # straight line is kept as the distance floor, so a graph miss costs
        # the polyline but never invents a shorter-than-impossible walk.
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
                # The access walk runs from the rider's point to the first
                # station, so it has no station object at its end and no
                # to_name. It does walk *to* that station, so name it --
                # otherwise the map's first milestone is labelled with the
                # instruction "Marcher 99 m ... jusqu'a X" instead of "X".
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
        # Prefer the edge the search actually traversed: it carries the REAL
        # along-geometry distance, time and polyline, so the reported step
        # equals the optimized cost and can be drawn accurately.
        edge = router.edge_between(a_id, b_id, line_used)
        seg_m = edge.distance_m if edge else straight_m
        seg_geom = edge.geometry if edge else []

        # A walk edge is a real pedestrian leg, not a ride: surface it as its
        # own walk step so the itinerary reads "walk, ride, walk" instead of
        # silently absorbing the transfer into the following ride.
        if line_used is None and seg_m > 1:
            # Upgrade a straight-lined transfer walk to the real pedestrian
            # path now that we know this leg is on the itinerary. The edge's
            # own polyline is the fallback, so a graph miss degrades to
            # exactly what it showed before.
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
                # Station ids let the API layer look up real geometry for
                # this leg in data/route_geometry.json.
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

        # A "ride" with no line and no distance is the same station appearing
        # twice on the path (two stops that share a coordinate, or a station
        # reached by a zero-length walk). Emitting it produced steps whose
        # start == end and whose line was an empty string -- visible to the
        # client as a rider "riding" between a point and itself. Skip it;
        # the surrounding steps already account for the movement.
        if line_used is None:
            continue

        # Report the USER-FACING mode (B1). Raw seed mode was "rail" for a
        # metro-tagged line in some records; the client must not have to
        # know that mapping.
        mode = router.user_mode_of_line.get(line_used or "", "bus") or "bus"
        ride_m = seg_m
        # Prefer REAL TRACK over cached geometry for rail modes. The cache
        # covers only 1 776 of ~3 900 station pairs and the gaps are almost all
        # rail, so a missing cached segment rendered as a straight line -- the
        # "jumps to the next station then comes back" artefact.
        #
        # The cached geometry is NOT discarded. It stays the fallback when
        # the two points are not on one connected track, and the result is
        # length-checked against the crow-flies distance so no impossible
        # sub-straight-line path can be accepted.
        if mode in ("train", "metro", "tram"):
            live_rail = paths.rail(a["lat"], a["lon"], b["lat"], b["lon"])
            if live_rail is not None and live_rail[1] >= 0.95 * straight_m:
                seg_geom = live_rail[0]
                seg_m = live_rail[1]
                edge = None  # force re-timing from the real track distance

        # Speed lookup must use the RAW seed mode, not the user-facing one.
        # canonical_mode() folds seed "rail" into "train", but SPEED_BY_MODE
        # rates them differently (train 60 km/h, rail 55 km/h), so passing
        # the canonical name silently re-timed every regional-rail leg and
        # changed which route the search picked.
        raw_mode = router.mode_of_line.get(line_used or "", "bus") or "bus"
        # Buses follow roads, so the road network can provide real geometry
        # when the precomputed cache is missing a segment.
        if not seg_geom and mode == "bus" and straight_m >= GEOMETRY_REQUIRED_M:
            live_bus = paths.road(a["lat"], a["lon"], b["lat"], b["lon"], "car")
            if live_bus is not None and live_bus[1] >= 0.95 * straight_m:
                seg_geom = live_bus[0]
                seg_m = live_bus[1]
                edge = None  # force re-timing from the real road distance
        ride_min = (
            (edge.time_s / 60.0)
            if edge
            else (ride_m / 1000 / transit_speed_kmh(raw_mode) * 60)
        )

        prev_line = path_lines[i]  # line arrived on at a
        # Boarding wait is paid when starting a new line (first boarding or
        # transfer). It is already in the search cost; surface it here so the
        # displayed duration matches the optimized cost.
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
                # Name the interchange, for the same reason as the access
                # walk: without to_name the client can only show
                # "Correspondance : marcher jusqu'a X", which buries a place
                # name inside a sentence instead of naming the place.
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
            # Station ids let the API layer look up real geometry for
            # this leg in data/route_geometry.json.
            "from_id": a_id,
            "to_id": b_id,
            "distance_m": round(ride_m),
            "duration_min": round(display_ride_min, 1),
            "wait_min": round(wait_min, 1),
            "time_seconds": round(display_ride_min * 60, 1),
            "geometry": seg_geom,
            "straight_m": round(straight_m),
            # No polyline on a leg long enough for the omission to be
            # visible. The client uses this to refuse a straight line
            # rather than draw one across open country.
            "needs_geometry": bool(
                not seg_geom and straight_m >= GEOMETRY_REQUIRED_M
            ),
            "label": f"{mode} — {a.get('name', '')} → {b.get('name', '')}{wait_label}",
        })
        total_min += display_ride_min
        prev_lat, prev_lon = b["lat"], b["lon"]
        prev_name = b.get("name", "")

    # Final leg: walk when it is a walkable gap, otherwise an explicit local
    # taxi hop. Labelled as such so the gap between the network and the
    # destination is visible to the user instead of being hidden behind one
    # straight line across the map.
    if s_end and s_end.get("lat") and s_end.get("lon"):
        straight_walk_m = haversine_m(prev_lat, prev_lon, end_lat, end_lon)
        # Route the gap in the mode it will actually be travelled: a short
        # gap is walked (pedestrian ways, steps, footways), while a gap past
        # MAX_END_WALK_METERS is a local taxi hop and must follow drivable
        # roads. Routing a 40 km taxi hop on the foot network would send it
        # down footpaths and stairs.
        leg_mode = "foot" if straight_walk_m <= MAX_END_WALK_METERS else "car"
        live = paths.road(prev_lat, prev_lon, end_lat, end_lon, leg_mode)
        walk_m = straight_walk_m
        walk_geom = []
        if live is not None and live[1] >= 0.95 * straight_walk_m:
            walk_geom, walk_m = live[0], live[1]
        if walk_m > 1:
            # Same rule as the cost branch in route(): distance decides, so
            # the rendered leg and the optimised cost can never disagree about
            # what this leg is. A long final gap is only a taxi hop when a
            # car-based mode is actually selected. Otherwise (e.g. bus-only, or
            # walking-only) it must stay a walk -- emitting a taxi leg the user
            # did not select is what made "bus only" return a bus+taxi itinerary.
            hop_permitted = allowed_modes is None or bool(allowed_modes & TAXI_MODES)
            if walk_m > MAX_END_WALK_METERS and hop_permitted:
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
