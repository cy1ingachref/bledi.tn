"""Streaming reader for the roads.gpkg GeoPackage -> road features.

Pure stdlib. The GeoPackage geometry blob is a short header (magic 'GP',
version, flags, srs_id, optional envelope) followed by standard WKB, so it
can be decoded without GDAL/shapely, which are not installed on this host.

Yields RoadFeature(highway, name, oneway, coords) with coords as
[(lon, lat), ...] straight out of WKB.
"""

from __future__ import annotations

import sqlite3
import os
import struct
from dataclasses import dataclass
from typing import Iterator, Sequence

WKB_POINT = 1
WKB_LINESTRING = 2
WKB_POLYGON = 3
WKB_MULTIPOINT = 4
WKB_MULTILINESTRING = 5
WKB_MULTIPOLYGON = 6
WKB_GEOMETRYCOLLECTION = 7

_ENVELOPE_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}


@dataclass(slots=True)
class RoadFeature:
    highway: str
    name: str | None
    name_fr: str | None
    name_ar: str | None
    oneway: str | None
    bridge: str | None
    coords: list[tuple[float, float]]  # [(lon, lat), ...]


def _blob_to_wkb(blob: bytes) -> memoryview:
    """Strip the GeoPackage binary header, return the WKB payload."""
    if len(blob) < 8 or blob[0:2] != b"GP":
        raise ValueError("not a GeoPackage geometry blob")
    flags = blob[3]
    little = bool(flags & 0x01)
    env_code = (flags >> 1) & 0x07
    empty = bool(flags & 0x10)
    env_len = _ENVELOPE_DOUBLES[env_code]
    off = 8 + env_len * 8
    # srs_id is int32 and envelope is already accounted for, so nothing else to
    # skip between the header and the WKB.
    if empty:
        return memoryview(b"")
    return memoryview(blob)[off:]


def _read_geom(view: memoryview, little: bool) -> tuple[int, list[tuple[float, float]]]:
    """Return (geometry_type, [(lon, lat), ...]) for one WKB geometry.

    `view` starts at the 1-byte endianness marker, so the type code is at
    offset 1. Reading it at offset 0 silently merges the endianness byte into
    the type (1 -> 0x01000000 | ...) and makes every feature fail to decode.
    """
    e = "<" if little else ">"
    if not view:
        raise ValueError("empty WKB")
    (gtype,) = struct.unpack_from(e + "I", view, 1)
    off = 5
    has_z = bool(gtype & 0x80000000)
    has_m = bool(gtype & 0x40000000)
    base = gtype & 0x0FFFFFFF
    ndim = 2 + (1 if has_z else 0) + (1 if has_m else 0)

    pts: list[tuple[float, float]] = []
    if base == WKB_POINT:
        (n,) = struct.unpack_from(e + "I", view, off)
        off += 4
        xs = struct.unpack_from(e + f"{n * ndim}d", view, off)
        for i in range(n):
            pts.append((xs[i * ndim], xs[i * ndim + 1]))
        off += 8 * ndim * n
    elif base == WKB_LINESTRING:
        (n,) = struct.unpack_from(e + "I", view, off)
        off += 4
        xs = struct.unpack_from(e + f"{n * ndim}d", view, off)
        for i in range(n):
            pts.append((xs[i * ndim], xs[i * ndim + 1]))
        off += 8 * ndim * n
    elif base in (WKB_POLYGON, WKB_MULTIPOINT):
        (nrings,) = struct.unpack_from(e + "I", view, off)
        off += 4
        for _ in range(nrings):
            (n,) = struct.unpack_from(e + "I", view, off)
            off += 4
            xs = struct.unpack_from(e + f"{n * ndim}d", view, off)
            for i in range(n):
                pts.append((xs[i * ndim], xs[i * ndim + 1]))
            off += 8 * ndim * n
    elif base in (WKB_MULTILINESTRING, WKB_MULTIPOLYGON, WKB_GEOMETRYCOLLECTION):
        (nparts,) = struct.unpack_from(e + "I", view, off)
        off += 4
        for _ in range(nparts):
            sub_type, sub_pts = _read_geom(view[off:], little)
            pts.extend(sub_pts)
            off += _geom_size(view[off:], little)
    else:
        raise ValueError(f"unsupported WKB type {base}")
    return base, pts


def _geom_size(view: memoryview, little: bool) -> int:
    """Byte length of one WKB geometry, same 1-byte-endianness layout."""
    e = "<" if little else ">"
    (gtype,) = struct.unpack_from(e + "I", view, 1)
    ndim = 2 + (1 if gtype & 0x80000000 else 0) + (1 if gtype & 0x40000000 else 0)
    base = gtype & 0x0FFFFFFF
    if base == WKB_POINT:
        return 5 + 4 + 8 * ndim
    if base == WKB_LINESTRING:
        (n,) = struct.unpack_from(e + "I", view, 5)
        return 9 + 8 * ndim * n
    if base in (WKB_POLYGON, WKB_MULTIPOINT):
        (nr,) = struct.unpack_from(e + "I", view, 5)
        total = 9
        for _ in range(nr):
            (n,) = struct.unpack_from(e + "I", view, total)
            total += 4 + 8 * ndim * n
        return total
    if base in (WKB_MULTILINESTRING, WKB_MULTIPOLYGON, WKB_GEOMETRYCOLLECTION):
        (np_,) = struct.unpack_from(e + "I", view, 5)
        off = 9
        for _ in range(np_):
            off += _geom_size(view[off:], little)
        return off
    raise ValueError(f"unsupported WKB type {base}")


def parse_geometry(blob: bytes) -> list[tuple[float, float]]:
    """[(lon, lat), ...] for a GeoPackage geometry blob (lines; area rings)."""
    if not blob:
        return []
    flags = blob[3]
    little = bool(flags & 0x01)
    view = _blob_to_wkb(blob)
    if not view:
        return []
    _, pts = _read_geom(view, little)
    return pts


def iter_roads(
    gpkg_path: str,
    table: str = "roads",
    batch: int = 20000,
    cols: Sequence[str] = (
        "geom",
        "highway",
        "name",
        "name_fr",
        "name_ar",
        "oneway",
        "bridge",
    ),
) -> Iterator[RoadFeature]:
    """Stream every feature of the roads table without loading it all in RAM."""
    uri = "file:" + gpkg_path.replace("\\", "/") + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT " + ",".join(cols) + f" FROM {table}")
        while True:
            rows = cur.fetchmany(batch)
            if not rows:
                break
            for geom, highway, name, name_fr, name_ar, oneway, bridge in rows:
                if not geom or not highway:
                    continue
                try:
                    pts = parse_geometry(geom)
                except (ValueError, struct.error):
                    continue
                if len(pts) < 2:
                    continue
                yield RoadFeature(
                    highway=highway,
                    name=name,
                    name_fr=name_fr,
                    name_ar=name_ar,
                    oneway=oneway,
                    bridge=bridge,
                    coords=pts,
                )
    finally:
        con.close()


if __name__ == "__main__":
    import collections
    import sys

    import os
    from pathlib import Path

    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get(
            "BLEDI_ROADS_GPKG", str(Path.home() / "Downloads" / "roads" / "roads.gpkg")
        )
    )
    counts: collections.Counter[str] = collections.Counter()
    verts = 0
    named = 0
    n = 0
    for f in iter_roads(path):
        counts[f.highway] += 1
        verts += len(f.coords)
        named += 1 if (f.name or f.name_fr) else 0
        n += 1
    print(f"features={n} vertices={verts} named={named}")
    for k, v in counts.most_common():
        print(f"  {k:24s} {v}")