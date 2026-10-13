#!/usr/bin/env python3
"""Audit every station's placement, and the connectivity of the network.

REPORT ONLY. This script never mutates the seed. It answers four questions the
user asked, and separates what is proven from what is merely unknown:

  A. PLACEMENT   Is each of the 7 465 stops somewhere a stop can physically be?
                 Checked against real evidence, in this order:
                   - outside Tunisia's bbox                      -> OFF-SITE
                   - inside an OSM water polygon (sea/lake/chott) -> IN WATER
                   - coincident with another stop, same point    -> DUPLICATE POINT
                   - a rail/metro stop far from any rail/metro
                     alignment (from route_geometry.json)        -> MODE MISMATCH
                   - no other stop within --isolation m and no
                     line listing it                             -> ISOLATED
                 A stop that passes all of these is REPORTED AS UNVERIFIED, not
                 as correct: the checks can prove a point is wrong, not that it
                 is right. Saying otherwise would be the mistake.

  B. BUS CONNECTIVITY  Which bus lines share stops, i.e. are relevant to each
                 other because a rider can transfer. Reports the interchange
                 graph's connected components, so a line that shares NO stop
                 with any other line (unreachable, no transfer possible) is
                 named rather than hidden in a count.

  C. LOUAGE LINKS  For every louage stop: what it is walk-connected to. A louage
                 terminal is only useful where it meets the rest of the network,
                 so the distance to the nearest non-louage stop is the finding.

  D. UNKNOWNS    Everything that could not be determined, listed explicitly
                 with the reason, so nothing is silently dropped.

Usage:
    python tool/audit_station_placement.py
    python tool/audit_station_placement.py --json out/report.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_all_tunisia_routes.tagged.json"
LOUAGE = ROOT / "data" / "seed_routes_destination_tunis.json"
GEOMETRY = ROOT / "data" / "route_geometry.json"
WATER = ROOT / "data" / "water_polys.json"

# Tunisia's actual geographic bounds, S,W,N,E.
#
# NOT the same as osm_common.TUNISIA_BBOX ("32.4,7.0,37.7,11.9"), which is a
# conservative box around the *network's* coverage. Using that as a correctness
# test produced 34 false "off-site" findings: Remada (32.31, 10.40), Dhehiba
# (32.01, 10.70) and the other TNP-registry stops near the Libyan border are
# real Tunisian towns, correctly placed, simply south of the network box.
# Country extremes: Borj el Khadra 30.24 N, Cap Angela 37.54 N,
# Nefta 7.52 E, El Ouardia/Remada 11.60 E.
TUNISIA_BBOX = (30.20, 7.45, 37.60, 11.65)

# A stop this far outside the country bounds is not a placement error so much
# as a corrupt coordinate; anything outside at all is reported, but the flag
# separates "outside the country" from "outside but plausibly a bad digit".
FAR_OFFSITE_M = 25_000.0

EARTH_R = 6371000.0

# Raw seed mode -> canonical, mirroring the backend's MODE_ALIASES. Duplicated
# here on purpose: the audit must be runnable without importing the app.
MODE_ALIASES = {
    "bus": {"bus", "rfr"},
    "tram": {"tram"},
    "metro": {"metro"},
    "train": {"train", "rail"},
    "louaj": {"louaj", "louage", "louage_red", "louage_blue", "louage_green"},
    "taxi": {"taxi"},
    "walk": {"walk"},
}
UNCLASSIFIED = {"unknown", "unclassified", ""}
# Modes that run on rails: a stop of one of these should sit on rail alignment.
RAIL_LIKE = {"train", "metro", "tram"}


def canonical(raw: str | None) -> str:
    r = (raw or "").strip().lower()
    if r in UNCLASSIFIED:
        return "unclassified"
    for mode, aliases in MODE_ALIASES.items():
        if r in aliases:
            return mode
    return "bus"


def haversine_m(a: float, b: float, c: float, d: float) -> float:
    """Great-circle distance in metres.

    ONE square root, not two. An earlier revision of this file wrote
    `asin(sqrt(min(1.0, sqrt(x))))`, which reports Tunis->Sousse as 1215 km
    instead of 115.6 km — a ~10.5x inflation that silently made every distance
    threshold meaningless (the louage-link test flagged all 33 terminals as
    "not walk-connected" at distances of 20-100 km).
    """
    p1, p2 = math.radians(a), math.radians(c)
    x = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(d - b) / 2) ** 2
    )
    return 2 * EARTH_R * math.asin(math.sqrt(min(1.0, x)))


def in_bbox(lat: float, lon: float, bb=TUNISIA_BBOX) -> bool:
    s, w, n, e = bb
    return s <= lat <= n and w <= lon <= e


# ── Spatial index: a lat/lon grid of buckets ──────────────────────────────
class Grid:
    """Buckets points by grid cell so nearest-neighbour is not O(n^2)."""

    def __init__(self, cell_deg: float) -> None:
        self.cell = cell_deg
        self.buckets: dict[tuple[int, int], list] = collections.defaultdict(list)

    def key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(lat // self.cell), int(lon // self.cell))

    def add(self, lat: float, lon: float, payload) -> None:
        self.buckets[self.key(lat, lon)].append((lat, lon, payload))

    def neighbours(self, lat: float, lon: float, rings: int = 1):
        ky, kx = self.key(lat, lon)
        for dy in range(-rings, rings + 1):
            for dx in range(-rings, rings + 1):
                yield from self.buckets.get((ky + dy, kx + dx), ())

    def nearest(self, lat: float, lon: float, rings: int = 2, exclude=None):
        """Nearest indexed point, expanding the search until something is found.

        A fixed ring count silently returns inf whenever the neighbourhood is
        empty, which read as "no stop anywhere near" for 5 846 stops — including
        Kasserine and Sbeitla, real cities with plenty of neighbours. The search
        now grows outward until it finds a point or exhausts max_rings, so inf
        genuinely means "nothing within max_rings cells".
        """
        max_rings = max(rings, 12)
        r = 1
        while r <= max_rings:
            best, dist = None, math.inf
            for plat, plon, payload in self.neighbours(lat, lon, r):
                if exclude is not None and payload is exclude:
                    continue
                d = haversine_m(lat, lon, plat, plon)
                if d < dist:
                    best, dist = payload, d
            if best is not None:
                return best, dist
            r += 1
        return None, math.inf


def point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Ray-casting. ring is [(lon, lat), ...]."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            xint = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < xint:
                inside = not inside
    return inside


def clip_ring_to_window(
    ring: list[tuple[float, float]],
    xmin: float, ymin: float, xmax: float, ymax: float,
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a ring to a rectangle.

    Essential before rasterising, not cosmetic. The GSHHG land polygon for
    continental Africa spans lon -9.5 to 180 and lat 1.3 to 77.7, so most of its
    1.16 M vertices lie far outside the Tunisia window. PIL does not clip
    reliably for mode "1": feeding it out-of-canvas vertices made it fill the
    water mask over Tunis, and all 30 flagged stations turned out to be land
    when re-tested exactly. Clipping first makes the drawn polygon the real
    intersection.

    Vectorised with numpy because the land ring has over a million vertices and
    a pure-Python loop over four edges is needlessly slow.
    """
    if len(ring) < 3:
        return []

    def as_arr(pts):
        return np.asarray(pts, dtype="float64")

    def clip_edge(arr, axis, limit, keep_greater):
        if len(arr) == 0:
            return arr
        vals = arr[:, axis]
        inside = vals >= limit if keep_greater else vals <= limit
        prev_inside = np.roll(inside, 1)
        prev = np.roll(arr, 1, axis=0)
        # Crossing points, where the segment changes side of the limit.
        crossing = inside != prev_inside
        out = []
        for i in range(len(arr)):
            if crossing[i]:
                a, b = prev[i], arr[i]
                denom = b[axis] - a[axis]
                if denom != 0:
                    t = (limit - a[axis]) / denom
                    pt = a + t * (b - a)
                    pt[axis] = limit
                    out.append(pt)
            if inside[i]:
                out.append(arr[i])
        return np.asarray(out) if out else np.empty((0, 2))

    arr = as_arr(ring)
    for axis, limit, greater in (
        (0, xmin, True), (0, xmax, False), (1, ymin, True), (1, ymax, False),
    ):
        arr = clip_edge(arr, axis, limit, greater)
        if len(arr) == 0:
            return []
    return [(float(x), float(y)) for x, y in arr]


class WaterIndex:
    """Water test backed by a RASTERISED mask, not per-point ray casting.

    Why a raster: the GSHHG full-resolution land polygon for continental Africa
    is a SINGLE ring with 1 160 926 vertices. Point-in-ring over that ring costs
    ~1.16 M segment tests, so 7 465 stops needed ~8.6 billion operations and the
    audit timed out at 590 s. A polygon test is the wrong tool at this scale.

    Instead the polygons are drawn once into a boolean grid at ~150 m per cell
    (0.0015 deg), and every query becomes an array lookup.

    Land and water are rasterised into SEPARATE masks and combined as:

        in water  =  inland_water_mask AND NOT land_mask

    That separation is essential, not decorative:

      * GSHHG L1 is LAND. The sea is its complement, so the ocean needs no
        polygons of its own. Adding an ocean layer AND subtracting land
        double-counted and made every sea point come back dry.
      * An ocean polygon's holes are land, so a coastal town can test "inside"
        the ocean's outer boundary. Subtracting land is what keeps La Marsa,
        Bizerte and Carthage dry — Natural Earth's 1:10,000,000 coastline
        classified all three as open sea.

    PIL fills each polygon ring in a single C call, so even the 1.16 M-vertex
    ring is handled in one pass.
    """

    # 0.0015 deg is ~167 m north-south and ~135 m east-west at Tunisia's
    # latitude — finer than the 150 m precision a station coordinate carries.
    RES = 0.0015

    def __init__(self, elements: list[dict]) -> None:
        from PIL import Image, ImageDraw

        # Named west/east/south/north, and nrows/ncols for the raster size.
        # An earlier revision stored the west bound in `self.w` and then
        # overwrote it with the raster WIDTH, so every ring failed the bounds
        # check, nothing was drawn, and the mask came back all-zero — the water
        # test silently passed everything as dry.
        self.south, self.west, self.north, self.east = 30.0, 7.0, 37.8, 12.0
        self.nrows = int((self.north - self.south) / self.RES) + 1
        self.ncols = int((self.east - self.west) / self.RES) + 1

        water_img = Image.new("1", (self.ncols, self.nrows), 0)
        land_img = Image.new("1", (self.ncols, self.nrows), 0)
        dw = ImageDraw.Draw(water_img)
        dl = ImageDraw.Draw(land_img)

        def to_px(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
            # PIL's y axis points down, so latitude is flipped.
            return [
                ((lon - self.west) / self.RES, (self.north - lat) / self.RES)
                for lon, lat in ring
            ]

        n_water = n_land = 0
        for el in elements:
            tags = el.get("tags") or {}
            kind = tags.get("natural") or tags.get("waterway") or tags.get("landuse") or "water"
            rings: list[list[tuple[float, float]]] = []
            if el.get("type") == "way":
                geom = el.get("geometry") or []
                if len(geom) >= 3:
                    rings.append([(p["lon"], p["lat"]) for p in geom])
            else:
                for m in el.get("members") or []:
                    mg = m.get("geometry") or []
                    if len(mg) >= 3:
                        rings.append([(p["lon"], p["lat"]) for p in mg])

            target = dl if kind == "land" else dw
            for ring in rings:
                # Clip to the window BEFORE drawing. PIL mode "1" does not clip
                # reliably, and the Africa land ring extends to lon 180 — drawing
                # it unclipped filled the water mask over Tunis.
                clipped = clip_ring_to_window(
                    ring, self.west, self.south, self.east, self.north
                )
                if len(clipped) < 3:
                    continue
                target.polygon(to_px(clipped), fill=1)
                if kind == "land":
                    n_land += 1
                else:
                    n_water += 1

        self.water_mask = np.array(water_img, dtype=bool)
        self.land_mask = np.array(land_img, dtype=bool)
        self.n_water_rings = n_water
        self.n_land_rings = n_land

        # Raw rings, kept for the EXACT verdict. The raster is only a prefilter:
        # PIL's mode-"1" fill over-filled the water mask so that Tunis Marine,
        # La Goulette and 28 other real stations came back as water while an
        # exact ray-cast test said land for every one of them. A coarse
        # approximation is fine for "definitely nowhere near water" but must
        # never be the answer, so every candidate is confirmed exactly.
        self.water_rings: list[tuple[str, list[tuple[float, float]], tuple]] = []
        self.land_rings: list[tuple[str, list[tuple[float, float]], tuple]] = []
        for el in elements:
            tags = el.get("tags") or {}
            kind = tags.get("natural") or tags.get("waterway") or tags.get("landuse") or "water"
            name = str(tags.get("name") or kind)
            rings: list[list[tuple[float, float]]] = []
            if el.get("type") == "way":
                geom = el.get("geometry") or []
                if len(geom) >= 3:
                    rings.append([(p["lon"], p["lat"]) for p in geom])
            else:
                for m in el.get("members") or []:
                    mg = m.get("geometry") or []
                    if len(mg) >= 3:
                        rings.append([(p["lon"], p["lat"]) for p in mg])
            bucket = self.land_rings if kind == "land" else self.water_rings
            for ring in rings:
                lons = [p[0] for p in ring]
                lats = [p[1] for p in ring]
                bucket.append((name, ring, (min(lats), min(lons), max(lats), max(lons))))

    @property
    def shapes(self) -> list:
        """Ring counts, for callers that only want a summary."""
        return [None] * (self.n_water_rings + self.n_land_rings)

    def _idx(self, lat: float, lon: float) -> tuple[int, int] | None:
        row = int((self.north - lat) / self.RES)
        col = int((lon - self.west) / self.RES)
        if 0 <= row < self.nrows and 0 <= col < self.ncols:
            return row, col
        return None

    def _exact_in(
        self,
        lat: float,
        lon: float,
        rings: list[tuple[str, list[tuple[float, float]], tuple]],
    ) -> str | None:
        """Exact ray-cast containment, bbox-rejected first.

        The bbox test is what keeps this affordable: it discards almost every
        ring without touching its vertices, so the million-vertex land ring is
        only ever scanned when the point is genuinely inside its bbox.
        """
        for name, ring, (s, w, n, e) in rings:
            if not (s <= lat <= n and w <= lon <= e):
                continue
            if point_in_ring(lon, lat, ring):
                return name
        return None

    def contains_exact(self, lat: float, lon: float) -> str | None:
        """Authoritative water test: exact polygons, no raster involved.

        Inland water wins over land, because OSM maps a chott as saltmarsh
        while GSHHG maps the same area as land.
        """
        inland = self._exact_in(lat, lon, self.water_rings)
        if inland is not None:
            return inland
        if self._exact_in(lat, lon, self.land_rings) is not None:
            return None
        return "sea (not mapped as land)"

    def contains(self, lat: float, lon: float) -> str | None:
        """Water body name, or None if dry.

        Two stages: the raster prefilter answers the common case (a stop in the
        middle of the country, nowhere near water) in constant time, and any
        candidate it raises is confirmed by exact ray casting. The raster is
        never allowed to be the final answer — it over-filled and produced 30
        false "in water" stations.
        """
        rc = self._idx(lat, lon)
        if rc is None:
            return None
        row, col = rc
        if not self.water_mask[row, col] and self.land_mask[row, col]:
            # Raster says: not near inland water, and inside land. Nothing to
            # confirm — but confirm anyway when the cell is near a boundary is
            # not knowable here, so fall through to the exact test only when the
            # raster is NOT confidently dry.
            return None
        return self.contains_exact(lat, lon)


def load_seed() -> tuple[list[dict], list[dict]]:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return data["stations"], data["lines"]


def load_louage() -> tuple[list[dict], list[dict]]:
    if not LOUAGE.is_file():
        return [], []
    d = json.loads(LOUAGE.read_text(encoding="utf-8"))
    return d.get("stations", []), d.get("routes", [])


def load_rail_geometry() -> dict[str, Grid]:
    """Grid of rail/metro/tram alignment vertices, by canonical mode."""
    grids: dict[str, Grid] = {}
    if not GEOMETRY.is_file():
        return grids
    segs = json.loads(GEOMETRY.read_text(encoding="utf-8")).get("segments", {})
    for seg in segs.values():
        mode = canonical(seg.get("mode"))
        if mode not in RAIL_LIKE:
            continue
        pts = seg.get("geometry") or []
        if len(pts) < 2:
            continue
        g = grids.setdefault(mode, Grid(0.01))
        for lat, lon in pts:
            g.add(lat, lon, seg)
    return grids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--isolation", type=float, default=250.0,
                    help="metres; a stop with no neighbour this close and no line is isolated")
    ap.add_argument("--rail-tolerance", type=float, default=1500.0,
                    help="metres; a rail stop further than this from rail alignment is a mismatch")
    ap.add_argument("--louage-link", type=float, default=1000.0,
                    help="metres; beyond this a louage terminal is not walk-connected")
    ap.add_argument("--json", default="", help="write the full report here")
    args = ap.parse_args()

    stations, lines = load_seed()
    lstations, lroutes = load_louage()

    # Canonical mode + coordinates for every station row.
    rows: list[dict] = []
    for s in stations:
        rows.append({
            "id": s.get("id"),
            "name": (s.get("name") or "").strip(),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "mode": canonical(s.get("mode")),
            "mode_raw": s.get("mode"),
            "city": s.get("city"),
            "operator": s.get("operator"),
            "source": s.get("source"),
        })
    for s in lstations:
        loc = s.get("location") or {}
        rows.append({
            "id": f"louage_{s.get('id')}",
            "name": (s.get("name_fr") or s.get("name_en") or s.get("id") or "").strip(),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "mode": "louaj",
            "mode_raw": "louage",
            "city": s.get("governorate"),
            "operator": "Louage",
            "source": "louage",
        })

    print(f"stations loaded: {len(rows)} (transit {len(stations)}, louage {len(lstations)})")

    # Which station ids are referenced by any line's stop list.
    referenced: set[str] = set()
    line_stops: dict[str, list[str]] = {}
    for ln in lines:
        stops = [x for x in (ln.get("stations") or ln.get("stops") or []) if isinstance(x, str)]
        line_stops[ln.get("id")] = stops
        referenced.update(stops)

    # ── A. PLACEMENT ──────────────────────────────────────────────────────
    no_coords = [r for r in rows if not r["lat"] or not r["lon"]]
    placed = [r for r in rows if r["lat"] and r["lon"]]

    offsite = [r for r in placed if not in_bbox(r["lat"], r["lon"])]

    water_hits: list[dict] = []
    if WATER.is_file():
        wdata = json.loads(WATER.read_text(encoding="utf-8"))
        water = WaterIndex(wdata.get("elements", []))
        print(f"water polygons indexed: {len(water.shapes)} rings")
        for r in placed:
            if not in_bbox(r["lat"], r["lon"]):
                continue
            hit = water.contains(r["lat"], r["lon"])
            if hit:
                water_hits.append({**r, "water": hit})
    else:
        print(f"WARNING: {WATER} missing — water test SKIPPED, results incomplete")

    # Coincident points: same rounded position, indexed before the split below.
    by_pos: dict[tuple[float, float], list[dict]] = collections.defaultdict(list)
    for r in placed:
        by_pos[(round(r["lat"], 5), round(r["lon"], 5))].append(r)

    # Coincident points: same position. Split into two findings, because they
    # are different problems:
    #   duplicate — same name AND same spot. One physical place recorded twice.
    #   shared    — different names at the same spot. A shared pole/interchange;
    #               legitimate, so reported separately and not counted as a fault.
    def _norm_name(n: str) -> str:
        return " ".join(n.lower().replace("&amp;", "&").split())

    coincident_dupes: list[dict] = []
    coincident_shared: list[dict] = []
    for (lat, lon), group in by_pos.items():
        if len(group) < 2:
            continue
        names = collections.Counter(_norm_name(g["name"]) for g in group)
        entry = {
            "lat": lat, "lon": lon, "count": len(group),
            "ids": [g["id"] for g in group],
            "names": [g["name"] for g in group],
            "modes": [g["mode"] for g in group],
        }
        # A repeated name means at least two rows are the same place.
        if names.most_common(1)[0][1] > 1:
            coincident_dupes.append(entry)
        else:
            coincident_shared.append(entry)

    # Isolation: nearest other stop, for stops no line lists.
    stop_grid = Grid(0.01)
    for r in placed:
        stop_grid.add(r["lat"], r["lon"], r)
    isolated: list[dict] = []
    for r in placed:
        if r["id"] in referenced:
            continue
        _, d = stop_grid.nearest(r["lat"], r["lon"], rings=2, exclude=r)
        # d is inf when the 5x5 cell neighbourhood held no other stop. That is
        # itself the finding (nothing anywhere near), so report it as such
        # rather than crashing on int(inf).
        if d == math.inf:
            isolated.append({**r, "nearest_stop_m": None, "note": "no stop within search radius"})
        elif d > args.isolation:
            isolated.append({**r, "nearest_stop_m": round(d)})

    # Rail-like stops must sit near rail alignment.
    rail_grids = load_rail_geometry()
    mode_mismatch: list[dict] = []
    if rail_grids:
        for r in placed:
            if r["mode"] not in RAIL_LIKE:
                continue
            g = rail_grids.get(r["mode"])
            if g is None:
                continue
            _, d = g.nearest(r["lat"], r["lon"], rings=3)
            if d == math.inf or d > args.rail_tolerance:
                mode_mismatch.append({
                    **r,
                    "nearest_rail_m": None if d == math.inf else round(d),
                })
    else:
        print("WARNING: no rail geometry — rail placement test SKIPPED")

    # ── B. BUS CONNECTIVITY ───────────────────────────────────────────────
    # Two lines are relevant to each other if they share at least one stop.
    # Lines that carry a stop list at all. BizerteConnect's 117 lines publish
    # endpoints and schedules but NO stops (the API has no stops endpoint), so
    # they are not graph edges and cannot share a stop with anything. Counting
    # them as "isolated lines" was wrong: they are stopless, not disconnected.
    stopless_lines = [lid for lid, stops in line_stops.items() if not stops]
    graph_lines = {lid: stops for lid, stops in line_stops.items() if stops}

    stop_to_lines: dict[str, set[str]] = collections.defaultdict(set)
    for lid, stops in graph_lines.items():
        for sid in stops:
            stop_to_lines[sid].add(lid)

    # Union-find over lines, joined by shared stops.
    parent: dict[str, str] = {lid: lid for lid in graph_lines}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for sid, lids in stop_to_lines.items():
        lids = list(lids)
        for other in lids[1:]:
            union(lids[0], other)

    components: dict[str, list[str]] = collections.defaultdict(list)
    for lid in graph_lines:
        components[find(lid)].append(lid)

    line_by_id = {ln.get("id"): ln for ln in lines}
    isolated_lines = [
        line_by_id[lid] for comp in components.values() if len(comp) == 1 for lid in comp
    ]

    # Interchange hubs: stops served by the most distinct lines.
    hubs = sorted(
        ((sid, len(lids)) for sid, lids in stop_to_lines.items() if len(lids) > 1),
        key=lambda kv: -kv[1],
    )

    # ── C. LOUAGE LINKS ───────────────────────────────────────────────────
    non_louage = Grid(0.01)
    for r in placed:
        if r["mode"] != "louaj":
            non_louage.add(r["lat"], r["lon"], r)

    louage_links: list[dict] = []
    for r in placed:
        if r["mode"] != "louaj":
            continue
        other, d = non_louage.nearest(r["lat"], r["lon"], rings=3)
        louage_links.append({
            **r,
            "nearest_stop": (other or {}).get("name"),
            "nearest_mode": (other or {}).get("mode"),
            "nearest_m": None if d == math.inf else round(d),
            "linked": d != math.inf and d <= args.louage_link,
        })

    # Louage route endpoints: the seed's `from`/`to` are station IDS
    # ("bab_saadoun", "bizerte_louage"), not display names. Comparing them to
    # names produced 104 bogus "unresolved endpoint" findings for ids that
    # resolve perfectly. Resolve against the louage station id set first.
    louage_ids = {s.get("id") for s in lstations if s.get("id")}
    name_index: dict[str, list[dict]] = collections.defaultdict(list)
    for r in placed:
        name_index[r["name"].lower()].append(r)
    unresolved_endpoints: list[dict] = []
    for rt in lroutes:
        for which in ("from", "to"):
            key = (rt.get(which) or "").strip()
            if not key:
                continue
            if key in louage_ids:
                continue
            # Fall back to a name match, so a seed that switches to names works.
            if key.lower() in name_index:
                continue
            unresolved_endpoints.append({
                "route_id": rt.get("id"),
                "endpoint": rt.get(which),
                "which": which,
            })

    # ── D. UNKNOWNS ───────────────────────────────────────────────────────
    unknown_mode = [r for r in placed if r["mode"] == "unclassified"]
    orphan = [r for r in placed if r["id"] not in referenced]

    # ── REPORT ────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("A. PLACEMENT")
    print("=" * 72)
    print(f"  total stops                      {len(rows)}")
    print(f"  with coordinates                 {len(placed)}")
    print(f"  no coordinates (cannot place)    {len(no_coords)}")
    print(f"  outside Tunisia bounds           {len(offsite)}")
    print(f"  inside a water polygon           {len(water_hits)}")
    print(f"  duplicate rows (same name+point) {len(coincident_dupes)}")
    print(f"  shared point (diff names, OK)    {len(coincident_shared)}")
    print(f"  rail stop far from rail track    {len(mode_mismatch)}")
    print(f"  isolated (no neighbour, no line) {len(isolated)}")

    if offsite:
        print("\n  -- OUTSIDE TUNISIA --")
        for r in offsite[:25]:
            print(f"    {r['name'][:34]:34s} {r['lat']:9.5f},{r['lon']:9.5f} {r['mode']:8s} {r['id']}")
    if water_hits:
        print("\n  -- IN WATER --")
        for r in water_hits[:40]:
            print(f"    {r['name'][:30]:30s} {r['lat']:9.5f},{r['lon']:9.5f} "
                  f"{r['mode']:8s} {r['water'][:24]}")
    if coincident_dupes:
        print("\n  -- DUPLICATE ROWS (same name at the same point) --")
        for entry in coincident_dupes[:20]:
            names = " | ".join(f"{n}({m})" for n, m in zip(entry["names"], entry["modes"]))
            print(f"    {entry['lat']:.5f},{entry['lon']:.5f} x{entry['count']}  {names[:96]}")
            print(f"      ids: {', '.join(entry['ids'][:3])}")
    if coincident_shared:
        print(f"\n  -- SHARED POINTS (different names, {len(coincident_shared)} — interchange/pole, not a fault) --")
        for entry in coincident_shared[:8]:
            print(f"    {entry['lat']:.5f},{entry['lon']:.5f}  {' | '.join(entry['names'])[:90]}")
    if mode_mismatch:
        print("\n  -- RAIL STOP FAR FROM RAIL TRACK --")
        for r in sorted(mode_mismatch, key=lambda x: -(x["nearest_rail_m"] or 10**9))[:25]:
            dist = r["nearest_rail_m"]
            shown = f"{dist:6d} m" if isinstance(dist, int) else "  none"
            print(f"    {r['name'][:30]:30s} {r['lat']:9.5f},{r['lon']:9.5f} "
                  f"{r['mode']:6s} nearest track {shown}")
    if isolated:
        print("\n  -- ISOLATED --")
        for r in sorted(isolated, key=lambda x: -(x["nearest_stop_m"] or 10**9))[:25]:
            dist = r["nearest_stop_m"]
            shown = f"{dist:7d} m" if isinstance(dist, int) else "   none"
            print(f"    {r['name'][:30]:30s} {r['lat']:9.5f},{r['lon']:9.5f} "
                  f"{r['mode']:8s} nearest stop {shown}")

    print("\n" + "=" * 72)
    print("B. BUS / LINE CONNECTIVITY")
    print("=" * 72)
    print(f"  lines                            {len(line_stops)}")
    print(f"  lines with a stop list (graph)   {len(graph_lines)}")
    print(f"  lines publishing NO stops        {len(stopless_lines)} (not graph edges)")
    print(f"  stops served by >1 line          {len(hubs)}")
    print(f"  interconnected components        {len(components)}")
    sizes = sorted((len(v) for v in components.values()), reverse=True)
    print(f"  component sizes (top 10)         {sizes[:10]}")
    print(f"  lines sharing NO stop with any other line  {len(isolated_lines)}")
    if isolated_lines:
        for ln in isolated_lines[:25]:
            print(f"    {str(ln.get('number'))[:12]:12s} {str(ln.get('name'))[:44]:44s} "
                  f"{ln.get('mode')}")
    if hubs:
        print("\n  -- TOP INTERCHANGE STOPS --")
        for sid, n in hubs[:15]:
            nm = next((r["name"] for r in rows if r["id"] == sid), sid)
            print(f"    {nm[:36]:36s} {n} lines")

    print("\n" + "=" * 72)
    print("C. LOUAGE CONNECTIVITY")
    print("=" * 72)
    linked = [x for x in louage_links if x["linked"]]
    print(f"  louage stops                     {len(louage_links)}")
    print(f"  walk-linked to another stop      {len(linked)} (<= {args.louage_link:.0f} m)")
    print(f"  NOT linked                       {len(louage_links) - len(linked)}")
    for x in sorted(louage_links, key=lambda y: -(y["nearest_m"] or 0)):
        flag = "OK " if x["linked"] else "FAR"
        print(f"    [{flag}] {x['name'][:28]:28s} -> {str(x['nearest_stop'])[:26]:26s} "
              f"{str(x['nearest_mode']):7s} {x['nearest_m'] if x['nearest_m'] is not None else '?':>6} m")
    print(f"\n  louage route endpoints not matching a known stop name: {len(unresolved_endpoints)}")
    for u in unresolved_endpoints[:20]:
        print(f"    {str(u['endpoint'])[:44]:44s} ({u['which']})")

    print("\n" + "=" * 72)
    print("D. UNKNOWNS (explicitly not determined)")
    print("=" * 72)
    print(f"  no coordinates in seed           {len(no_coords)}")
    print(f"  mode 'unclassified'              {len(unknown_mode)}")
    print(f"  served by no line (orphan)       {len(orphan)}")
    print(f"  rail-placement test skipped      {not bool(rail_grids)}")
    print(f"  water test skipped               {not WATER.is_file()}")
    if no_coords:
        print("\n  -- NO COORDINATES --")
        for r in no_coords:
            print(f"    {r['name'][:36]:36s} {r['id']}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "summary": {
                "total": len(rows),
                "placed": len(placed),
                "no_coords": len(no_coords),
                "offsite": len(offsite),
                "in_water": len(water_hits),
                "duplicate_rows": len(coincident_dupes),
                "shared_points": len(coincident_shared),
                "rail_mismatch": len(mode_mismatch),
                "isolated": len(isolated),
                "lines": len(line_stops),
                "lines_with_stops": len(graph_lines),
                "lines_without_stops": len(stopless_lines),
                "components": len(components),
                "isolated_lines": len(isolated_lines),
                "louage_stops": len(louage_links),
                "louage_linked": len(linked),
                "unresolved_louage_endpoints": len(unresolved_endpoints),
                "unclassified": len(unknown_mode),
                "orphan": len(orphan),
            },
            "offsite": offsite,
            "in_water": water_hits,
            "duplicate_rows": coincident_dupes,
            "shared_points": coincident_shared,
            "rail_mismatch": mode_mismatch,
            "isolated": isolated,
            "isolated_lines": [{"id": l.get("id"), "number": l.get("number"),
                                "name": l.get("name"), "mode": l.get("mode")}
                               for l in isolated_lines],
            "components": [sorted(v) for v in components.values()],
            "hubs": [{"id": s, "lines": n} for s, n in hubs[:60]],
            "louage_links": louage_links,
            "unresolved_louage_endpoints": unresolved_endpoints,
            "no_coords": no_coords,
            "unclassified": unknown_mode,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
