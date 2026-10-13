#!/usr/bin/env python3
"""Build data/water_polys.json from GSHHG coastline + Geofabrik OSM inland water.

Sources, and why each:

  SEA  — GSHHG (Global Self-consistent Hierarchical High-resolution Geography),
         full resolution (f), levels 1 and 2. ~100 m coastline accuracy.
         Natural Earth 10m was tried first and is NOT usable here: it is a
         1:10,000,000 generalisation, so its coastline swallows whole coastal
         towns. It classified La Marsa, Bizerte and Carthage as open sea, while
         Nominatim confirms all three are residential land. That is the exact
         false-positive that makes a water audit worthless.
         GSHHG L1 = land, L2 = lake, L3 = island-in-lake, L4 = pond-in-island.
         Land and islands are the COMPLEMENT of water; they are stored here as
         "land" so the index can subtract them rather than testing rings blindly.

  INLAND — Geofabrik's Tunisia extract (gis_osm_water_a_free_1.shp). OSM's own
         polygons, including 153 saltmarsh features for the chotts and 530
         reservoirs. Natural Earth carries no Tunisian lakes at all.

Ring semantics matter: GSHHG land polygons have the ocean as holes, and an
ocean polygon's holes are land. Testing each ring independently would report
half of Tunisia as sea. The index therefore stores land rings separately and
treats a point as water only if it is inside a water ring AND not inside a land
ring.

    python tool/build_water_polys.py --gshhg C:/tmp/gshhg --geofabrik C:/tmp/tunis_shp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "water_polys.json"

# Tunisia + a margin.
BBOX = (30.0, 7.0, 37.8, 12.0)

WATER_FCLASSES = {
    "water", "reservoir", "wetland", "riverbank", "dock",
    "wetland_marsh", "wetland_bog",
    "wetland_reedbed", "wetland_tidalflat", "wetland_swamp",
}

LAND_FCLASSES = {
    # A chott is a dry salt flat for most of the year, so it is treated as LAND:
    # Tozeur and its bus stops sit on its edge and must not be flagged "in
    # water" by a wetland polygon that is flooded only seasonally.
    "wetland_saltmarsh",
}


def _clip(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Clip a ring to the audit window (Sutherland-Hodgman).

    Done at BUILD time, not per query. The GSHHG land polygon for continental
    Africa is a single ring of 1 160 926 vertices; clipping it to Tunisia leaves
    a few thousand. That is what makes the audit's exact water test affordable
    without a raster shortcut — and the raster shortcut was lossy (it skipped
    two stops that are genuinely in the sea).
    """
    xmin, ymin, xmax, ymax = BBOX[1], BBOX[0], BBOX[3], BBOX[2]
    if len(ring) < 3:
        return []

    def clip_edge(pts, axis, limit, keep_greater):
        if not pts:
            return []
        out = []
        prev = pts[-1]
        prev_in = (prev[axis] >= limit) if keep_greater else (prev[axis] <= limit)
        for cur in pts:
            cur_in = (cur[axis] >= limit) if keep_greater else (cur[axis] <= limit)
            if cur_in != prev_in:
                denom = cur[axis] - prev[axis]
                if denom != 0:
                    t = (limit - prev[axis]) / denom
                    out.append((prev[0] + t * (cur[0] - prev[0]),
                                prev[1] + t * (cur[1] - prev[1])))
            if cur_in:
                out.append(cur)
            prev, prev_in = cur, cur_in
        return out

    pts = list(ring)
    for axis, limit, greater in ((0, xmin, True), (0, xmax, False),
                                 (1, ymin, True), (1, ymax, False)):
        pts = clip_edge(pts, axis, limit, greater)
        if len(pts) < 3:
            return []
    return pts


def _rings(shape) -> list[list[tuple[float, float]]]:
    pts = shape.points
    parts = list(shape.parts) + [len(pts)]
    out = []
    for i in range(len(parts) - 1):
        ring = pts[parts[i]:parts[i + 1]]
        if len(ring) >= 4:
            clipped = _clip([(float(x), float(y)) for x, y in ring])
            if len(clipped) >= 3:
                out.append(clipped)
    return out


def _in_window(ring: list[tuple[float, float]]) -> bool:
    s, w, n, e = BBOX
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return not (max(lats) < s or min(lats) > n or max(lons) < w or min(lons) > e)


def from_gshhg(dirp: Path, level: int, kind: str) -> list[dict]:
    """GSHHS_<res>_L<level>.shp -> rings tagged with `kind` (land or water)."""
    import shapefile

    # Full resolution is "f". Fall back to high ("h") if f is absent.
    for res in ("f", "h"):
        p = dirp / "GSHHS_shp" / res / f"GSHHS_{res}_L{level}.shp"
        if p.is_file():
            break
    else:
        print(f"MISSING GSHHG level {level} under {dirp}")
        return []

    reader = shapefile.Reader(str(p))
    out: list[dict] = []
    for sr in reader.shapeRecords():
        for ring in _rings(sr.shape):
            if not _in_window(ring):
                continue
            out.append({
                "type": "way",
                "id": len(out) + 1,
                "tags": {"natural": kind, "name": f"GSHHG L{level}"},
                "geometry": [{"lon": lo, "lat": la} for lo, la in ring],
            })
    print(f"gshhg L{level} ({kind}) {p.parent.name}/{p.name}: {len(out)} rings")
    return out


def from_geofabrik(path: Path) -> list[dict]:
    import shapefile

    reader = shapefile.Reader(str(path))
    fields = [f[0] for f in reader.fields[1:]]
    fi = fields.index("fclass")
    ni = fields.index("name") if "name" in fields else None

    out: list[dict] = []
    for sr in reader.shapeRecords():
        fclass = sr.record[fi]
        if fclass in LAND_FCLASSES:
            kind = "land"
        elif fclass in WATER_FCLASSES:
            kind = "water"
        else:
            continue
        name = str(sr.record[ni] or fclass) if ni is not None else fclass
        for ring in _rings(sr.shape):
            if not _in_window(ring):
                continue
            out.append({
                "type": "way",
                "id": len(out) + 1,
                "tags": {"natural": fclass, "name": name},
                "geometry": [{"lon": lo, "lat": la} for lo, la in ring],
                "kind": kind,
            })
    print(f"geofabrik {path.name}: {len(out)} rings")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gshhg", required=True, help="dir containing GSHHS_shp/")
    ap.add_argument("--geofabrik", required=True, help="dir with gis_osm_water_a_free_1.shp")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    gdir = Path(args.gshhg)
    gpath = Path(args.geofabrik) / "gis_osm_water_a_free_1.shp"
    if not gpath.is_file():
        print(f"MISSING: {gpath}")
        return 1

    elements: list[dict] = []
    # Land first (levels 1 and 3), then water. Order does not matter to the
    # index because it keeps the two sets apart, but keeping them contiguous
    # makes the file readable.
    elements += from_gshhg(gdir, 1, "land")      # continents / main land
    elements += from_gshhg(gdir, 3, "land")      # islands inside lakes
    elements += from_gshhg(gdir, 2, "water")     # major lakes
    elements += from_geofabrik(gpath)            # OSM inland water

    if not elements:
        print("FAILED: nothing built")
        return 1

    out = Path(args.out)
    out.write_text(
        json.dumps({
            "elements": elements,
            "bbox": BBOX,
            "source": ("gshhg-2.3.7 full-res L1/L3 land + L2 lakes; "
                       "geofabrik tunisia-latest-free water polygons"),
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    kinds: dict[str, int] = {}
    for el in elements:
        k = el.get("kind") or el["tags"]["natural"]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"\nwrote {out} — {len(elements)} rings, {out.stat().st_size / 1e6:.1f} MB")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
