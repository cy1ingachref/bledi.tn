"""The transit graph: one directed edge per consecutive stop pair, plus walk edges."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from bledi_transit.domain.geo import haversine_m, oriented_geometry, polyline_length
from bledi_transit.domain.modes import TAXI_MODES, canonical_mode
from bledi_transit.domain.tunables import GEOMETRY_REQUIRED_M, SPEED_BY_MODE, WALK_SPEED_MS

Segments = dict[str, dict[str, Any]]

# The line of a walk edge. After a walk the next boarding pays its wait again,
# and the sentinel never equals a real line id.
WALK_EDGE = "__walk__"

# Sentinel line id for louage-taxi transfer edges. Distinct from WALK_EDGE so
# the router can tell a mode-to-mode transfer from a walk-to-stop transfer.
LOUAGE_TAXI_EDGE = "__louage_taxi_transfer__"

# Radius for connecting louage and taxi stations as transfer hubs.
LOUAGE_TAXI_TRANSFER_RADIUS_M = 500.0

# Stations closer than this (or with the same normalised name) are treated as
# the same physical interchange: zero-cost transfer.
LOUAGE_TAXI_SAME_LOCATION_M = 50.0


def transit_speed_kmh(mode: str) -> float:
    return SPEED_BY_MODE.get(mode, SPEED_BY_MODE["bus"])


def transit_speed_ms(mode: str) -> float:
    return transit_speed_kmh(mode) / 3.6


@dataclass(slots=True)
class Edge:
    """One directed graph edge.

    distance_m follows the geometry when there is one, so the cost model and
    the drawn line agree. Empty `geometry` means no real path was found.
    """
    to_id: str
    line: str
    mode: str
    wait_s: float
    distance_m: float
    time_s: float
    geometry: list[list[float]]
    straight_m: float

    @property
    def needs_geometry(self) -> bool:
        return not self.geometry and self.straight_m >= GEOMETRY_REQUIRED_M


def line_edge(
    segments: Segments,
    a_id: str,
    b_id: str,
    a: dict[str, Any],
    b: dict[str, Any],
    ln_id: str,
    mode: str,
    wait_s: float,
) -> Edge:
    """One directed ride edge with real distance, time and geometry."""
    straight_m = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    entry = segments.get(f"{min(a_id, b_id)}|{max(a_id, b_id)}")
    geom: list[list[float]] = []
    real_m = straight_m
    if entry and entry.get("geometry"):
        geom = oriented_geometry(entry, a_id, b_id)
        # Shorter than the straight line means a mis-oriented or mis-stitched
        # slice in the cache.
        cand_m = polyline_length(geom)
        if cand_m >= 0.95 * straight_m:
            real_m = cand_m
        else:
            geom = []
    if real_m <= 0:
        real_m = straight_m
    return Edge(
        to_id=b_id,
        line=ln_id,
        mode=mode,
        wait_s=wait_s,
        distance_m=real_m,
        time_s=real_m / transit_speed_ms(mode),
        geometry=geom,
        straight_m=straight_m,
    )


def add_walk_edges(
    adj: dict[str, list[Edge]],
    stations: dict[str, dict[str, Any]],
    walk_segments: Segments,
    max_walk_edge_m: float,
) -> None:
    """Connect nearby stops with bidirectional walk edges.

    Without them a stop no line calls at is unreachable. A grid of
    walk-radius cells replaces the O(n^2) scan, which would add seconds to
    every start.
    """
    pos: dict[str, tuple[float, float]] = {
        sid: (s["lat"], s["lon"])
        for sid, s in stations.items()
        if s.get("lat") and s.get("lon")
    }
    cell_deg = max(max_walk_edge_m, 100) / 111_000.0
    grid: dict[tuple[int, int], list[str]] = defaultdict(list)
    for sid, (lat, lon) in pos.items():
        grid[(int(lat / cell_deg), int(lon / cell_deg))].append(sid)

    span = 1 if max_walk_edge_m <= cell_deg * 2 else 2
    for sid, (lat, lon) in pos.items():
        cx, cy = int(lat / cell_deg), int(lon / cell_deg)
        for dx in range(-span, span + 1):
            for dy in range(-span, span + 1):
                for other in grid.get((cx + dx, cy + dy), ()):
                    # Both cells see both stops, so without this guard every
                    # pair is built twice; the extra appends are exact duplicates.
                    if other <= sid:
                        continue
                    o_lat, o_lon = pos[other]
                    d = haversine_m(lat, lon, o_lat, o_lon)
                    if d > max_walk_edge_m:
                        continue
                    # Not live-routed: a live A* for each of the ~12 700 pairs
                    # would add minutes to startup. The itinerary resolves the
                    # real path only for the walks a rider sees.
                    wentry = walk_segments.get(f"{min(sid, other)}|{max(sid, other)}")
                    wgeom: list[list[float]] = []
                    wlen = d
                    if wentry and wentry.get("geometry"):
                        cand = oriented_geometry(wentry, sid, other)
                        cand_m = polyline_length(cand)
                        if cand_m >= 0.95 * d:
                            wgeom = cand
                            wlen = cand_m
                    for src, dst in ((sid, other), (other, sid)):
                        adj[src].append(
                            Edge(
                                to_id=dst,
                                line=WALK_EDGE,
                                mode="walk",
                                wait_s=0.0,
                                distance_m=wlen,
                                time_s=wlen / WALK_SPEED_MS,
                                geometry=wgeom,
                                straight_m=d,
                            )
                        )


def _normalise_name(name: str) -> str:
    """Normalise a station name for comparison: lowercase, strip, collapse spaces."""
    return " ".join((name or "").strip().lower().split())


def add_louage_taxi_transfers(
    adj: dict[str, list[Edge]],
    stations: dict[str, dict[str, Any]],
    louage_stations: list[dict[str, Any]] | None = None,
) -> int:
    """Connect louage and taxi stations with transfer edges.

    Louage and taxi are both road-for-hire modes that often serve the same
    physical hubs (e.g. a louage station and a taxi stand on the same square).
    Without explicit transfer edges the router cannot switch between them,
    even when they are 30 m apart.

    This function:

    1. Merges louage seed stations into the station dict (prefixed ``louage_``).
    2. Finds all stations whose canonical mode is ``louaj`` or ``taxi``.
    3. Creates bidirectional transfer edges between every louage-taxi pair
       within ``LOUAGE_TAXI_TRANSFER_RADIUS_M`` (default 500 m) that is not
       already connected by a walk edge.
    4. Creates zero-cost transfer edges for stations at the same physical
       location (same normalised name or < ``LOUAGE_TAXI_SAME_LOCATION_M``)
       that are not already connected.
    5. Connects any still-isolated louage seed station to the nearest
       main-seed station within ``LOUAGE_TAXI_TRANSFER_RADIUS_M``.

    Returns the number of transfer edges created.
    """
    # Merge louage seed stations into the station dict.
    louage_seed_ids: list[str] = []
    for ls in louage_stations or []:
        raw_id = ls.get("id") or ""
        if not raw_id:
            continue
        sid = f"louage_{raw_id}" if not raw_id.startswith("louage_") else raw_id
        if sid in stations:
            continue  # already present from the main seed
        loc = ls.get("location") or {}
        lat, lon = loc.get("lat"), loc.get("lon")
        if not lat or not lon:
            continue
        stations[sid] = {
            "id": sid,
            "name": ls.get("name_fr") or ls.get("name_en") or raw_id,
            "name_en": ls.get("name_en"),
            "lat": lat,
            "lon": lon,
            "mode": "louage",
            "source": "louage",
        }
        louage_seed_ids.append(sid)

    # Collect louage and taxi stations.
    louage_ids: list[str] = []
    taxi_ids: list[str] = []
    for sid, s in stations.items():
        if not s.get("lat") or not s.get("lon"):
            continue
        raw_mode = s.get("mode") or ""
        canon = canonical_mode(raw_mode)
        if canon in TAXI_MODES:
            if canon == "louaj":
                louage_ids.append(sid)
            else:
                taxi_ids.append(sid)

    edge_count = 0

    # Build a set of existing walk pairs to avoid duplicates.
    existing_walk_pairs: set[tuple[str, str]] = set()
    for src, edges in adj.items():
        for e in edges:
            if e.mode == "walk" and e.line == WALK_EDGE:
                existing_walk_pairs.add((src, e.to_id))

    # Helper to create a transfer edge.
    def _add_transfer(a_id: str, b_id: str, dist_m: float, zero_cost: bool) -> None:
        nonlocal edge_count
        if zero_cost:
            time_s = 0.0
            wait_s = 0.0
        else:
            time_s = dist_m / WALK_SPEED_MS
            wait_s = 0.0
        for src, dst in ((a_id, b_id), (b_id, a_id)):
            adj[src].append(
                Edge(
                    to_id=dst,
                    line=LOUAGE_TAXI_EDGE,
                    mode="walk",
                    wait_s=wait_s,
                    distance_m=dist_m if not zero_cost else 0.0,
                    time_s=time_s,
                    geometry=[[stations[src]["lat"], stations[src]["lon"]],
                              [stations[dst]["lat"], stations[dst]["lon"]]],
                    straight_m=dist_m,
                )
            )

    # Same-location transfers: zero-cost.
    for louage_id in louage_ids:
        louage_name = _normalise_name(stations[louage_id].get("name", ""))
        louage_lat = stations[louage_id]["lat"]
        louage_lon = stations[louage_id]["lon"]
        for taxi_id in taxi_ids:
            taxi_name = _normalise_name(stations[taxi_id].get("name", ""))
            taxi_lat = stations[taxi_id]["lat"]
            taxi_lon = stations[taxi_id]["lon"]
            same_name = louage_name and taxi_name and louage_name == taxi_name
            close = haversine_m(louage_lat, louage_lon, taxi_lat, taxi_lon) <= LOUAGE_TAXI_SAME_LOCATION_M
            if same_name or close:
                # Skip if already connected by a walk edge.
                if (louage_id, taxi_id) in existing_walk_pairs:
                    continue
                _add_transfer(louage_id, taxi_id, 0.0, zero_cost=True)
                edge_count += 1

    # Nearby transfers: walk-time cost within the radius.
    for louage_id in louage_ids:
        louage_lat = stations[louage_id]["lat"]
        louage_lon = stations[louage_id]["lon"]
        for taxi_id in taxi_ids:
            taxi_lat = stations[taxi_id]["lat"]
            taxi_lon = stations[taxi_id]["lon"]
            d = haversine_m(louage_lat, louage_lon, taxi_lat, taxi_lon)
            if d <= LOUAGE_TAXI_TRANSFER_RADIUS_M:
                # Skip if already linked as same-location or by a walk edge.
                same_name = (
                    _normalise_name(stations[louage_id].get("name", ""))
                    and _normalise_name(stations[louage_id].get("name", ""))
                    == _normalise_name(stations[taxi_id].get("name", ""))
                )
                if same_name or d <= LOUAGE_TAXI_SAME_LOCATION_M:
                    continue
                if (louage_id, taxi_id) in existing_walk_pairs:
                    continue
                _add_transfer(louage_id, taxi_id, d, zero_cost=False)
                edge_count += 1

    # Connect isolated louage seed stations to the nearest main-seed station.
    for louage_sid in louage_seed_ids:
        if adj.get(louage_sid):
            continue  # already has edges from the steps above
        louage_s = stations[louage_sid]
        best_id: str | None = None
        best_d = float("inf")
        for other_sid, other_s in stations.items():
            if other_sid == louage_sid:
                continue
            if not other_s.get("lat") or not other_s.get("lon"):
                continue
            d = haversine_m(louage_s["lat"], louage_s["lon"], other_s["lat"], other_s["lon"])
            if d < best_d and d <= LOUAGE_TAXI_TRANSFER_RADIUS_M:
                best_d = d
                best_id = other_sid
        if best_id:
            _add_transfer(louage_sid, best_id, best_d, zero_cost=False)
            edge_count += 1

    return edge_count