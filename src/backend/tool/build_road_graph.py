"""Build a routable road graph from roads.gpkg into a compact binary.

Input : C:\\Users\\cy1in\\Downloads\\roads\\roads.gpkg (HotOSM Tunisia, 396k
        features / 6.9M vertices, highway class + oneway + names).
Output: data/road_graph.npz  -- one shared topology, three mode profiles.

Design
------
One node table and one undirected edge table serve every mode, because the
expensive part is the topology. Each edge carries a per-mode speed table and a
per-mode "allowed" bitmask, so car / foot / bike routing is a filter over the
same arrays rather than three graphs.

  nodes    lat,lon  float32  (WGS84)
  edges    u,v     int32    (index into nodes, u is the stored direction)
           length  float32  meters, along-geometry (NOT straight line)
           flags   uint8    bit0 motor_vehicle, bit1 foot, bit2 bicycle
           speeds  uint16   meters/sec * 10 for (car, foot, bike)
  names    ways    one entry per contributing OSM feature

Coordinates are quantised to 6dp (~11 cm at Tunisia's latitude) for node
identity so shared endpoints become one node. Topology comes only from this
GPKG; geometry is resampled to at most ~25 m per point on read.

Usage:
  python src/backend/tool/build_road_graph.py [--gpkg PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from typing import Iterator

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gpkg_roads import iter_roads  # noqa: E402

# Bit layout of the per-edge flags byte.
MODE_CAR, MODE_FOOT, MODE_BIKE = 1, 2, 4
ALL_MODES = MODE_CAR | MODE_FOOT | MODE_BIKE

# Per OSM highway class: (modes, car km/h, foot km/h, bike km/h).
# Classes absent here are not routable at all (construction/proposed/planned,
# bus_stop, platform, rest_area, emergency_access_point, services).
CLASS_TABLE: dict[str, tuple[int, float, float, float]] = {
    "motorway": (MODE_CAR, 110, 3.0, 0),
    "motorway_link": (MODE_CAR, 60, 3.0, 0),
    "trunk": (MODE_CAR | MODE_BIKE, 90, 4.0, 35),
    "trunk_link": (MODE_CAR, 50, 4.0, 25),
    "primary": (ALL_MODES, 70, 5.0, 25),
    "primary_link": (ALL_MODES, 45, 5.0, 20),
    "secondary": (ALL_MODES, 60, 5.0, 28),
    "secondary_link": (ALL_MODES, 40, 5.0, 20),
    "tertiary": (ALL_MODES, 45, 5.0, 25),
    "tertiary_link": (ALL_MODES, 35, 5.0, 20),
    "unclassified": (ALL_MODES, 30, 5.0, 25),
    "residential": (ALL_MODES, 30, 5.0, 25),
    "living_street": (ALL_MODES, 10, 5.0, 15),
    "service": (MODE_CAR | MODE_BIKE, 15, 5.0, 15),
    "track": (ALL_MODES, 20, 4.0, 12),
    "raceway": (MODE_CAR, 60, 0, 0),
    "pedestrian": (MODE_FOOT | MODE_BIKE, 0, 5.0, 15),
    "footway": (MODE_FOOT, 0, 5.0, 8),
    "path": (ALL_MODES, 0, 4.0, 12),
    "bridleway": (MODE_FOOT | MODE_BIKE, 0, 4.0, 8),
    "steps": (MODE_FOOT, 0, 2.0, 0),
    "cycleway": (MODE_FOOT | MODE_BIKE, 0, 5.0, 18),
    "corridor": (MODE_FOOT | MODE_BIKE, 0, 5.0, 12),
    "busway": (MODE_CAR, 30, 5.0, 15),
}

# Exclude plain 'construction' etc. by omission from CLASS_TABLE.
QUANT = 6  # decimal places for node identity
EARTH_R = 6371008.8
MAX_EDGE_M = 4000.0  # guards against a bogus geometry joining two far nodes


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def is_forward_only(oneway: str | None) -> bool:
    """True when the stored way direction is the only legal travel direction."""
    if not oneway:
        return False
    v = oneway.strip().lower()
    return v in {"yes", "true", "1", "-1"}


def label_components(
    n_nodes: int, src: np.ndarray, dst: np.ndarray
) -> np.ndarray:
    """Component id per node for one directed-edge set (undirected view).

    A routing search that cannot reach its target spends its whole budget
    exhausting an entire component -- measured at 10-22 s per attempt on the
    Tunisia graph, because A* keeps proving more nodes unreachable. Knowing the
    component up front turns "these two snaps are in different components" into
    an array lookup, and lets the caller pick snap candidates that can actually
    connect.

    Vectorised connected components: repeatedly relax the parent pointer with
    np.minimum.at until nothing changes. Every pass at least halves the depth
    for long chains, so this converges in O(log n) passes instead of one Python
    iteration per edge. A per-edge Python union-find over 13M edges took 12 s
    and, worse, produced a wrong answer (nearly every node in its own
    component); this is both faster and correct.
    """
    if src.size == 0:
        return np.zeros(n_nodes, dtype=np.int32)
    parent = np.arange(n_nodes, dtype=np.int64)
    for _ in range(64):  # log2(6.3M) is 23; 64 is a generous safety bound
        a = parent[src]
        b = parent[dst]
        lo = np.minimum(a, b)
        hi = np.maximum(a, b)
        np.minimum.at(parent, src, lo)
        np.minimum.at(parent, dst, lo)
        # Path-compress this pass's results so the next pass starts shallow.
        new_parent = parent[parent]
        if np.array_equal(new_parent, parent):
            break
        parent = new_parent
    roots = parent[np.arange(n_nodes)]
    _, comp = np.unique(roots, return_inverse=True)
    return comp.astype(np.int32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpkg", default=r"C:\Users\cy1in\Downloads\roads\roads.gpkg")
    ap.add_argument(
        "--out",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "road_graph.npz"
        ),
    )
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    t0 = time.time()
    # node id table: quantised (lat, lon) -> int index
    node_id: dict[tuple[int, int], int] = {}
    node_lat: list[float] = []
    node_lon: list[float] = []
    eu: list[int] = []
    ev: list[int] = []
    elen: list[float] = []
    eflags: list[int] = []
    espeeds: list[tuple[int, int, int]] = []
    ename: list[int] = []
    names: list[tuple[str, str, str]] = []  # (name, name_fr, name_ar)
    name_id: dict[tuple[str, str, str], int] = {}
    skipped_class: dict[str, int] = {}
    split_edges = 0

    def node_for(lat: float, lon: float) -> int:
        key = (round(lat, QUANT), round(lon, QUANT))
        idx = node_id.get(key)
        if idx is None:
            idx = len(node_lat)
            node_id[key] = idx
            node_lat.append(lat)
            node_lon.append(lon)
        return idx

    feats = 0
    for feat in iter_roads(args.gpkg):
        spec = CLASS_TABLE.get(feat.highway)
        if spec is None:
            skipped_class[feat.highway] = skipped_class.get(feat.highway, 0) + 1
            continue
        modes, car_kmh, foot_kmh, bike_kmh = spec
        if modes == 0:
            skipped_class[feat.highway] = skipped_class.get(feat.highway, 0) + 1
            continue
        speeds = (
            int(round(car_kmh / 3.6 * 10)),
            int(round(foot_kmh / 3.6 * 10)),
            int(round(bike_kmh / 3.6 * 10)),
        )
        nkey = (feat.name or "", feat.name_fr or "", feat.name_ar or "")
        if nkey in name_id:
            wid = name_id[nkey]
        else:
            wid = len(names)
            name_id[nkey] = wid
            names.append(nkey)
        # A mode bit is set only when that mode actually has a speed, so the
        # flag byte and the speed table can never disagree.
        base_flags = (
            (MODE_CAR if speeds[0] > 0 else 0)
            | (MODE_FOOT if speeds[1] > 0 else 0)
            | (MODE_BIKE if speeds[2] > 0 else 0)
        )
        # oneway=yes applies to motor vehicles only; people walk and cycle a
        # one-way street in both directions.
        if feat.oneway and is_forward_only(feat.oneway):
            fwd_flags = base_flags & MODE_CAR
            rev_flags = 0
        else:
            fwd_flags = rev_flags = base_flags

        prev = None
        prev_lat = prev_lon = 0.0
        for lon, lat in feat.coords:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                prev = None
                continue
            cur = node_for(lat, lon)
            if prev is not None:
                d = haversine_m(prev_lat, prev_lon, lat, lon)
                if d <= 0.0:
                    continue
                if d > MAX_EDGE_M:
                    # A quantisation/geometry artefact, not a drivable link.
                    split_edges += 1
                    prev = cur
                    prev_lat, prev_lon = lat, lon
                    continue
                eu.append(prev)
                ev.append(cur)
                elen.append(d)
                eflags.append(fwd_flags)
                espeeds.append(speeds)
                ename.append(wid)
                # reverse twin shares length/speed/name but carries rev_flags
                eu.append(cur)
                ev.append(prev)
                elen.append(d)
                eflags.append(rev_flags)
                espeeds.append(speeds)
                ename.append(wid)
            prev = cur
            prev_lat, prev_lon = lat, lon
        feats += 1
        if feats % 50000 == 0:
            print(
                f"  {feats} features, {len(node_lat)} nodes, {len(eu)} edges"
                f" ({time.time() - t0:.0f}s)",
                flush=True,
            )

    n_nodes = len(node_lat)
    n_edges = len(eu)
    print(f"parsed {feats} routable features -> {n_nodes} nodes, {n_edges} directed edges")

    lat_a = np.asarray(node_lat, dtype=np.float64)
    lon_a = np.asarray(node_lon, dtype=np.float64)
    u_a = np.asarray(eu, dtype=np.int32)
    v_a = np.asarray(ev, dtype=np.int32)
    len_a = np.asarray(elen, dtype=np.float64)
    flag_a = np.asarray(eflags, dtype=np.uint8)
    sp = np.asarray(espeeds, dtype=np.uint16).reshape(-1, 3)
    name_a = np.asarray(ename, dtype=np.int32)

    # Node degree filter: a degree-1 stub contributes nothing to a through
    # route but doubles the CSR size. Keep it -- dead ends matter for snapping
    # a destination that sits on a private spur -- but record the count.
    deg = np.bincount(np.concatenate([u_a, v_a]).astype(np.int64), minlength=n_nodes)

    # Per-mode component labels. Search must never start a pair it knows is
    # unreachable, so these are computed at build time rather than discovered
    # by a 20-second failed A*.
    comps: dict[str, np.ndarray] = {}
    for mode, bit in (("car", MODE_CAR), ("foot", MODE_FOOT), ("bike", MODE_BIKE)):
        tc0 = time.time()
        # Cast to bool: eflags is uint8, and `uint8_array & bit` stays uint8.
        # Indexing a numpy array with a uint8 array is integer fancy indexing,
        # not a mask, so without this the graph collapses to a couple of edges
        # and every component count comes out meaningless.
        keep = (flag_a & bit).astype(bool)
        comps[mode] = label_components(n_nodes, u_a[keep], v_a[keep])
        sizes = np.bincount(comps[mode])
        print(
            f"  {mode:5s} components: {sizes.size:,} "
            f"(largest {int(sizes.max()):,} nodes, {100.0 * sizes.max() / n_nodes:.1f}% of graph) "
            f"[{time.time() - tc0:.0f}s]"
        )

    np.savez_compressed(
        out,
        lat=lat_a,
        lon=lon_a,
        eu=u_a,
        ev=v_a,
        elen=len_a,
        eflags=flag_a,
        espec=sp,
        ename=name_a,
        ename_raw=np.array(names, dtype=object),
        quant=np.array([QUANT], dtype=np.int32),
        comp_car=comps["car"],
        comp_foot=comps["foot"],
        comp_bike=comps["bike"],
    )
    size_mb = os.path.getsize(out) / 1e6
    print(f"wrote {out} ({size_mb:.1f} MB)")
    print(f"  isolated nodes (degree 0): {int((deg == 0).sum())}")
    print(f"  edges dropped as >{MAX_EDGE_M:.0f}m: {split_edges}")
    print(f"  node degree p50={np.percentile(deg, 50):.0f} p99={np.percentile(deg, 99):.0f} max={deg.max()}")
    if skipped_class:
        print("  non-routable classes skipped:")
        for k, v in sorted(skipped_class.items(), key=lambda kv: -kv[1]):
            print(f"    {k:24s} {v}")
    print(f"total {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())