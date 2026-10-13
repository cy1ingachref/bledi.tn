"""Build a routable RAIL/metro/tram graph, mirroring build_road_graph.py.

Why this exists
---------------
`data/route_geometry.json` holds 1 776 station-pair polylines, and the missing
ones are concentrated on rail: train_23_sncft alone lacks 6 of 17 stop pairs
(Tunis Ville -> Djebal Jelloud, Bouficha -> Enfida, ...). Every missing pair was
drawn as a STRAIGHT LINE, which is what made the map appear to jump to the next
town and come back.

This builds the network so geometry can be derived from the TRACK itself:
snap two points onto the nearest rail, A* along the rail. Line ids and numbers
are labels, never topology.

Input : C:\\Users\\cy1in\\Downloads\\rails\\export.geojson
        (OSM: 2 733 rail/light_rail/tram ways + 670 platform/station points)
Output: data/rail_graph.npz
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import math
import os
import sys
import time
from typing import Any, Iterator

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_road_graph import label_components  # noqa: E402

EARTH_R = 6371008.8
QUANT = 6               # node identity precision (~11 cm)

MODE_RAIL, MODE_LIGHT, MODE_TRAM = 1, 2, 4

# OSM railway value -> (mode bits, km/h). Absent here means "not track".
CLASS_TABLE: dict[str, tuple[int, float]] = {
    "rail": (MODE_RAIL, 60.0),
    "light_rail": (MODE_LIGHT, 32.0),
    "tram": (MODE_TRAM | MODE_LIGHT, 25.0),
    "subway": (MODE_LIGHT, 32.0),
    "narrow_gauge": (MODE_RAIL, 45.0),
    "funicular": (MODE_RAIL, 12.0),
    "monorail": (MODE_LIGHT, 30.0),
    "preserved": (MODE_RAIL, 25.0),
}
POINT_CLASSES = {"station", "halt", "platform", "stop_position"}

MAX_EDGE_M = 3000.0
# No minimum segment length: 40% of sampled rail segments are under 40 m, and
# those short hops are exactly what joins one OSM way to the next. Filtering
# them shattered the network into 27 716 components.
MIN_SEG_M = 0.0
# Ways meeting at a junction usually end a metre or two apart, not at the same
# coordinate. Endpoints closer than this are stitched into one node; without it
# the graph had 893 components with the largest holding only 8.4% of the nodes.
JUNCTION_M = 60.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def iter_track(path: str) -> Iterator[tuple[str, list[tuple[float, float]]]]:
    """Yield (railway_class, [(lon, lat), ...]) for every usable feature."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    def walk(geom: Any) -> Iterator[list[Any]]:
        if not isinstance(geom, dict):
            return
        t, c = geom.get("type"), geom.get("coordinates")
        if t == "Point" and c:
            yield [c]
        elif t == "LineString" and c:
            yield c
        elif t in ("MultiLineString", "MultiPoint") and c:
            for part in c:
                yield from walk({"type": "LineString", "coordinates": part})
        elif t == "GeometryCollection":
            for g in geom.get("geometries") or ():
                yield from walk(g)

    for feat in data.get("features") or ():
        rw = ((feat.get("properties") or {}).get("railway") or "").strip().lower()
        if rw not in CLASS_TABLE and rw not in POINT_CLASSES:
            continue
        for pts in walk(feat.get("geometry") or {}):
            if len(pts) >= 2 or (rw in POINT_CLASSES and len(pts) == 1):
                yield rw, [(float(p[0]), float(p[1])) for p in pts]


def stitch_endpoints(pts: list[tuple[float, float]]) -> list[int]:
    """Union-find over points, merging any two within JUNCTION_M.

    Returns a root index per input point. Used on way endpoints only, so the
    cost is proportional to the number of ways, not to the vertex count.
    """
    n = len(pts)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Bucket by ~JUNCTION_M so the neighbour scan stays local.
    cell = JUNCTION_M / 111_320.0
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, (lon, lat) in enumerate(pts):
        buckets.setdefault((int(lon // cell), int(lat // cell)), []).append(i)

    lim = (JUNCTION_M / 111_320.0) ** 2
    for (bi, bj), idxs in buckets.items():
        near: list[int] = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                near.extend(buckets.get((bi + di, bj + dj), ()))
        for i in idxs:
            li, la = pts[i]
            for j in near:
                if j <= i:
                    continue
                lj, lo_ = pts[j]
                if (lj - li) ** 2 + (lo_ - la) ** 2 <= lim:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
    return [find(i) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--rails",
        default=os.environ.get(
            "BLEDI_RAILS_GEOJSON", str(Path.home() / "Downloads" / "rails" / "export.geojson")
        ),
    )
    ap.add_argument(
        "--out",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "rail_graph.npz"
        ),
    )
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    t0 = time.time()
    tracks = [
        (cls, coords)
        for cls, coords in iter_track(args.rails)
        if cls not in POINT_CLASSES and len(coords) >= 2
    ]
    points = [
        (cls, coords) for cls, coords in iter_track(args.rails)
        if cls in POINT_CLASSES
    ]
    print(f"{len(tracks):,} track ways, {len(points):,} platform/station points")

    # Stitch way endpoints into junctions, once, up front.
    ends: list[tuple[float, float]] = []
    for _cls, coords in tracks:
        ends.append(coords[0])
        ends.append(coords[-1])
    roots = stitch_endpoints(ends)
    # root index -> one representative coordinate for that junction
    junction_of: dict[int, tuple[int, int]] = {}
    for (lon, lat), r in zip(ends, roots):
        junction_of.setdefault(r, (round(lat, QUANT), round(lon, QUANT)))
    print(f"{len(ends):,} endpoints -> {len(junction_of):,} junctions "
          f"({time.time() - t0:.0f}s)")

    node_id: dict[tuple[int, int], int] = {}
    lat_a: list[float] = []
    lon_a: list[float] = []

    eu: list[int] = []
    ev: list[int] = []
    elen: list[float] = []
    eflags: list[int] = []
    espeeds: list[tuple[int, int]] = []
    ename: list[int] = []
    names: list[tuple[str, str]] = []
    name_id: dict[str, int] = {}
    dropped = 0

    def emit(seq: list[tuple[int, int]], modes: int, speed: int, wid: int) -> None:
        nonlocal dropped
        for (ia, ja), (ib, jb) in zip(seq, seq[1:]):
            d = haversine_m(lat_a[ia], lon_a[ia], lat_a[ib], lon_a[ib])
            if d < MIN_SEG_M or d > MAX_EDGE_M or d <= 0.0:
                dropped += 1
                continue
            eu.append(ia); ev.append(ib); elen.append(d)
            eflags.append(modes); espeeds.append((speed, speed)); ename.append(wid)
            eu.append(ib); ev.append(ia); elen.append(d)
            eflags.append(modes); espeeds.append((speed, speed)); ename.append(wid)

    end_cursor = 0
    for cls, coords in tracks:
        modes, kmh = CLASS_TABLE[cls]
        speed = int(round(kmh / 3.6 * 10))
        if cls in name_id:
            wid = name_id[cls]
        else:
            wid = len(names)
            name_id[cls] = wid
            names.append((cls, ""))
        seq: list[tuple[int, int]] = []
        last_i = len(coords) - 1
        for i, (lon, lat) in enumerate(coords):
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                if len(seq) >= 2:
                    emit(seq, modes, speed, wid)
                seq = []
                continue
            # Endpoints (first and last) are rewritten onto their shared
            # junction, which is what stitches adjacent OSM ways into a
            # corridor. Interior vertices keep their own coordinate.
            if i in (0, last_i):
                key = junction_of.get(roots[end_cursor])
                end_cursor += 1
            else:
                key = (round(lat, QUANT), round(lon, QUANT))
            idx = node_id.get(key)
            if idx is None:
                idx = len(lat_a)
                node_id[key] = idx
                lat_a.append(lat)
                lon_a.append(lon)
            seq.append((idx, idx))
        if len(seq) >= 2:
            emit(seq, modes, speed, wid)

    # Platforms/stations: record nodes so a stop can snap to a served point.
    for _cls, coords in points:
        lon, lat = coords[0]
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            key = (round(lat, QUANT), round(lon, QUANT))
            if key not in node_id:
                node_id[key] = len(lat_a)
                lat_a.append(lat)
                lon_a.append(lon)

    n = len(lat_a)
    used = set(eu) | set(ev)
    print(f"  nodes referenced by an edge: {len(used):,} of {n:,} "
          f"({100.0 * len(used) / max(n, 1):.0f}%)")
    flags_a = np.asarray(eflags, dtype=np.uint8)
    comps = label_components(n, np.asarray(eu, dtype=np.int64), np.asarray(ev, dtype=np.int64))
    sizes = np.bincount(comps)
    print(f"built {n:,} nodes, {len(eu):,} directed edges "
          f"({dropped} segments dropped)")
    print(f"  components: {sizes.size:,} (largest {int(sizes.max()):,} nodes, "
          f"{100.0 * sizes.max() / max(n, 1):.1f}%)")
    if sizes.max() < n * 0.5:
        print("  WARNING: no dominant component -- network still fragmented")

    np.savez_compressed(
        out,
        lat=np.asarray(lat_a, dtype=np.float64),
        lon=np.asarray(lon_a, dtype=np.float64),
        eu=np.asarray(eu, dtype=np.int32),
        ev=np.asarray(ev, dtype=np.int32),
        elen=np.asarray(elen, dtype=np.float64),
        eflags=flags_a,
        espec=np.asarray(espeeds, dtype=np.uint16).reshape(-1, 2),
        ename=np.asarray(ename, dtype=np.int32),
        ename_raw=np.array(names, dtype=object),
        comp=comps,
    )
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB) in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())