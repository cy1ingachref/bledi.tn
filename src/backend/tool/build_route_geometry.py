#!/usr/bin/env python3
"""Precompute real route geometry for every transit segment in the seed.

Committed output: data/route_geometry.json. The app draws the route as a
straight line between consecutive stops because the seed carries no shape data
at all -- measured: 0 of 232 lines have a shape/polyline/geometry key. This
fetches actual geometry once so the map can draw the real path.

Two sources, by mode, because a train must follow the track and not the road:

  rail / metro / tram  OSM route relations (`type=route`, `route=rail|train|
                       light_rail|tram|monorail|light_rail`) resolved to their
                       member way geometry. This is the actual track: the
                       dedicated right-of-way, including tunnels and reserved
                       alignments that no driving profile can follow.

  bus                 OSRM driving profile, snapped to the nearest point on a
                       road. Tunisian bus routes share the road network and
                       there is no dependable OSM relation coverage for all 193
                       bus lines, so the road network is the honest best
                       available.

  walk                not fetched. Footways are not in the driving profile, and
                       the walk legs are short (<= 900 m) where the straight
                       line is visually indistinguishable. The frontend draws
                       these dashed and unlabelled as a deliberate approximation.

Writes a cache keyed by an unordered station-id pair, so it survives reordering
and works for both travel directions.

    python src/backend/tool/build_route_geometry.py
    python src/backend/tool/build_route_geometry.py --limit 20     # smoke test
    python src/backend/tool/build_route_geometry.py --resume        # continue

Refuses to overwrite a complete cache unless --force, and re-fetches only the
missing pairs when --resume is given. Segments that cannot be resolved are
recorded with a reason and no geometry, so the frontend falls back to a
straight line for those and the gap is auditable rather than silent.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
OUT_PATH = BASE / "data" / "route_geometry.json"

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "bledi-geometry/1.0 (Tunisia transit routing; github.com/cy1ingachref/bledi.tn)"

# OSM route= values that correspond to fixed-rail track, per mode.
RAIL_ROUTE_VALUES = ("rail", "train", "light_rail", "tram", "monorail", "subway")

# OSM railway= values to include as track geometry.
#
# In-service track only. Deliberately excluded: disused, abandoned,
# construction, proposed -- a train drawn onto a lifted or unbuilt track would be
# a lie, and those ways are numerous enough (244 disused + 218 abandoned + 66
# construction measured) to distort the network if included.
WAY_RAILWAY_VALUES = ("rail", "light_rail", "tram", "narrow_gauge", "funicular")

# Overpass bbox covering Tunisia.
BBOX = "30.2,7.4,37.6,12.2"

# Optional local OSM road network (HOTOSM GeoPackage), used to fill gaps that
# OSRM could not resolve. Offline and deterministic once present, which also
# removes ~1580 network calls from a full build. Point at the extracted
# roads.gpkg, or set BLEDI_ROADS_GPKG. Absent means OSRM-only, as before.
ROADS_GPKG = os.environ.get(
    "BLEDI_ROADS_GPKG", r"C:\Users\cy1in\Downloads\roads\roads.gpkg"
)

# highway= values a bus or taxi can use. Ordered by preference so the first
# match wins when several classes serve the same pair.
ROAD_DRIVE_CLASSES = (
    "residential", "unclassified", "tertiary", "tertiary_link", "secondary",
    "secondary_link", "primary", "primary_link", "trunk", "trunk_link",
    "motorway", "motorway_link", "living_street", "service", "track",
    "pedestrian", "footway", "path",
)

# A path along a network cannot be shorter than the straight line between its
# endpoints, so anything under this is a projection mistake rather than a route.
# Not optional: an early prototype without it reported 619 of 1210 walk legs
# "filled", including a 203 m hop that produced a 1 m stub, because two nearby
# stops projected onto adjacent vertices of the same cul-de-sac.
MIN_PATH_RATIO = 0.95

# A geometry is only trusted if it stays near the two stops it connects.
# The bound is split by mode because a single value rejected ~250 real bus
# segments. Measured on the rejected set (parsed from the stored reason
# strings): road/bus detours have min 2.01x, MEDIAN 3.05x, and 67% are within
# 4x. That is not a matcher failure -- a city bus on a one-way grid genuinely
# drives three times the crow-flies distance to serve two stops on opposite
# sides of a block. Rejecting them left those legs drawn as straight lines,
# which is the exact symptom this work exists to remove.
#
# Rail keeps the tight bound: measured rail rejections run 6.4x to 193x, so
# those really are OSM matching the wrong line, not a detour.
MAX_DETOUR_FACTOR = 2.0
MAX_DETOUR_FACTOR_ROAD = float(os.environ.get("MAX_DETOUR_FACTOR_ROAD", "4.0"))


def load_seed() -> dict:
    with SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def segments(stations: list[dict], lines: list[dict]) -> list[tuple[str, str, str]]:
    """Distinct (a, b, mode) transit segments, deduplicated across lines."""
    have = {s["id"] for s in stations if s.get("lat") and s.get("lon")}
    seen: dict[tuple[str, str], str] = {}
    for ln in lines:
        mode = ln.get("mode") or "bus"
        stops = [s for s in (ln.get("stations") or ln.get("stops") or []) if s in have]
        for a, b in zip(stops, stops[1:]):
            key = (a, b) if a < b else (b, a)
            # Prefer a rail interpretation if any line claims the pair as rail.
            prev = seen.get(key)
            if prev is None or (prev != "rail" and mode in ("train", "rail", "metro")):
                seen[key] = mode if prev is None else prev
    return [(a, b, m) for (a, b), m in seen.items()]


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(x), math.sqrt(1 - x))


# ── Overpass: real track geometry ──────────────────────────────────────────
def overpass(query: str, timeout: int = 180) -> list[dict] | None:
    """Run an Overpass query, retrying each mirror.

    Overpass returns 429/504 readily and the public mirrors are shared, so a
    single failure is usually a rate limit rather than a real outage: measured
    here, the identical query failed and then succeeded moments later. Each
    mirror therefore gets its own backoff before the next is tried.
    """
    data = urllib.parse.urlencode({"data": query}).encode()
    for url in OVERPASS_ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    # Read the body first. These responses run to tens of MB and
                    # streaming them through json.load can fail part-way on a
                    # truncated chunk; catching that here used to look like a dead
                    # mirror, and the caller read None as "zero ways fetched" and
                    # carried on with relations-only geometry.
                    body = resp.read()
                    payload = json.loads(body)
                    return payload.get("elements", [])
            except urllib.error.HTTPError as exc:
                host = url.split("/")[2]
                if exc.code in (429, 504):
                    backoff = 20 * (attempt + 1)
                    print(
                        f"    overpass {host} HTTP {exc.code} (rate limited), "
                        f"retrying in {backoff}s",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    continue
                print(
                    f"    overpass {host} HTTP {exc.code}: "
                    f"{exc.read()[:120].decode('utf-8', 'replace')}",
                    file=sys.stderr,
                )
                break
            except Exception as exc:  # noqa: BLE001 - network/DNS/timeout
                host = url.split("/")[2]
                print(f"    overpass {host} failed: {type(exc).__name__}", file=sys.stderr)
                time.sleep(10)
                break
    return None


def stitch(parts: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join way geometries into connected chains, preserving traversal order.

    This is essential, not cosmetic. An OSM route relation lists its member ways
    in no guaranteed order, so simply concatenating them produces a polyline whose
    vertex index has nothing to do with distance along the line. Measured on the
    Tunis-Mahdia relation: two stations 1.9 km apart projected onto indices 1432
    and 198, so the "slice between them" ran backwards through 1235 vertices and
    180 km of track. Joining ways end-to-end by shared endpoints fixes the
    ordering, after which index order is distance order.

    Returns every chain produced. A relation is usually one path, but may include
    a disconnected branch or two; those are returned separately rather than
    silently concatenated into something false.
    """
    if not parts:
        return []
    # Longest first: the backbone anchors the main chain and shorter ways attach
    # to it. Anything left over becomes its own chain.
    remaining = sorted(parts, key=len, reverse=True)
    chains: list[list[tuple[float, float]]] = []
    while remaining:
        chain = list(remaining.pop(0))
        grew = True
        while grew:
            grew = False
            choice = None
            for i, part in enumerate(remaining):
                if part[0] == chain[-1]:
                    at_end, reverse = True, False
                elif part[-1] == chain[-1]:
                    at_end, reverse = True, True
                elif part[-1] == chain[0]:
                    at_end, reverse = False, False
                elif part[0] == chain[0]:
                    at_end, reverse = False, True
                else:
                    continue
                if choice is None or len(part) > len(remaining[choice[0]]):
                    choice = (i, at_end, reverse)
            if choice is not None:
                i, at_end, reverse = choice
                part = remaining.pop(i)
                if reverse:
                    part = list(reversed(part))
                chain = chain + part if at_end else part + chain
                grew = True
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def load_rail_network() -> list[list[tuple[float, float]]]:
    """Build the Tunisian rail network as connected polylines.

    Two sources, and the second one is the important one. Route relations only
    cover ways somebody grouped into a route, so they account for 34 of the
    country's rail features. Querying plain `railway=*` ways returns 3,456 more
    -- sidings, freight branches, station approaches and rural lines that belong
    to no relation at all. Measured: median segment 47 m for the ways against
    581 m for Natural Earth 10m, i.e. the ways are 12x finer, and they are what
    makes a 400 m station hop resolvable at all.

    Only in-service track is taken. disused/abandoned/construction ways are
    excluded because drawing a train onto a lifted track would be a lie.

    Returns the polylines; node coordinates are no longer needed.
    """
    values = "|".join(RAIL_ROUTE_VALUES)
    parts: list[list[tuple[float, float]]] = []

    print("fetching OSM rail route relations...")
    rel_query = (
        f'[out:json][timeout:240];\n'
        f'rel["type"="route"]["route"~"^({values})$"]({BBOX});\n'
        f'out geom;'
    )
    rels = overpass(rel_query, timeout=300)
    if rels is None:
        print("  route relations unavailable; relying on plain ways", file=sys.stderr)
        rels = []
    for el in rels:
        member_parts: list[list[tuple[float, float]]] = []
        for m in el.get("members") or []:
            geom = m.get("geometry")
            if not geom:
                continue
            part = [(g["lat"], g["lon"]) for g in geom if g.get("lat") is not None]
            if len(part) >= 2:
                member_parts.append(part)
        parts.extend(stitch(member_parts))
    rel_chains = sum(1 for _ in parts)
    print(f"  {len(rels)} relations -> {rel_chains} chains")

    # The two queries hit the same shared Overpass service back to back.
    # Measured: issuing them together returns HTTP 504 on the second, and only
    # succeeds after a pause, so wait rather than hammer.
    time.sleep(15)
    print("fetching OSM railway ways (relations miss most of the network)...")
    way_query = (
        f'[out:json][timeout:300];\n'
        f'way["railway"~"^({"|".join(WAY_RAILWAY_VALUES)})$"]({BBOX});\n'
        f'out geom;'
    )
    ways = overpass(way_query, timeout=360)
    if ways is None:
        # Fatal on purpose. Returning relations-only here previously produced a
        # 62-chain network instead of ~1800 and silently lost the ways that fix
        # most rail gaps, so a fetch failure must stop the build.
        raise SystemExit(
            "Overpass unavailable: cannot fetch railway ways. "
            "Refusing to build relations-only geometry."
        )
    if not ways:
        raise SystemExit(
            "Overpass returned zero railway ways for Tunisia, which cannot be "
            "right (the count query alone reports 3456). Refusing to continue."
        )
    way_parts: list[list[tuple[float, float]]] = []
    for w in ways:
        geom = w.get("geometry")
        if not geom or len(geom) < 2:
            continue
        part = [(g["lat"], g["lon"]) for g in geom if g.get("lat") is not None]
        if len(part) >= 2:
            way_parts.append(part)
    print(f"  {len(way_parts)} ways")

    # Relations first so a route's own geometry wins a shared endpoint; then the
    # loose ways extend the network outwards from it.
    polylines = stitch(parts + way_parts)
    print(f"  total: {len(polylines)} chains, "
          f"{sum(len(c) for c in polylines):,} vertices")
    return polylines


ROAD_NET_CACHE = BASE / "data" / ".road_network_cache.json"


def load_road_network() -> list[list[tuple[float, float]]]:
    """Load the local OSM road network from the HOTOSM GeoPackage.

    The decoded network is memoised to data/.road_network_cache.json. Decoding
    the 232 MB GeoPackage and stitching it takes over four minutes, and both
    the transit build and the taxi build need it; without the cache a pair of
    concurrent runs each pay that cost and thrash on the same file.
    """
    if ROAD_NET_CACHE.exists():
        try:
            t = time.time()
            raw = json.loads(ROAD_NET_CACHE.read_text(encoding="utf-8"))
            src_mtime = (
                Path(ROADS_GPKG).stat().st_mtime if Path(ROADS_GPKG).exists() else 0
            )
            # Rebuild only when the source GeoPackage is newer than the cache.
            if raw.get("source_mtime") == src_mtime:
                chains = [[(p[0], p[1]) for p in c] for c in raw["chains"]]
                print(
                    f"  road network from cache: {len(chains):,} chains "
                    f"({time.time() - t:.1f}s)"
                )
                return chains
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  road cache unreadable ({exc}); decoding GeoPackage")

    chains = _decode_road_network()
    try:
        src_mtime = (
            Path(ROADS_GPKG).stat().st_mtime if Path(ROADS_GPKG).exists() else 0
        )
        ROAD_NET_CACHE.write_text(
            json.dumps(
                {
                    "source_mtime": src_mtime,
                    "chains": [[[p[0], p[1]] for p in c] for c in chains],
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        print(f"  wrote {ROAD_NET_CACHE.name}")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  could not write road cache: {exc}")
    return chains


def _decode_road_network() -> list[list[tuple[float, float]]]:
    """Decode and stitch the HOTOSM GeoPackage road network.

    Offline and deterministic: the same file always yields the same chains,
    which also removes roughly 1580 OSRM calls from a full build. Returns [] when
    the file is absent, and the caller then falls back to OSRM alone.

    The GeoPackage geometry blob is a small header followed by standard WKB:
    magic "GP", version, flags, srs_id, then an envelope whose length the flags
    encode, then the WKB. Decoding it directly avoids needing GDAL/ogr, which is
    not installed here.
    """
    if not ROADS_GPKG or not Path(ROADS_GPKG).exists():
        print(f"  no local road file at {ROADS_GPKG}; OSRM only")
        return []
    print(f"loading local road network from {Path(ROADS_GPKG).name}...")
    import sqlite3
    import struct

    allowed = set(ROAD_DRIVE_CLASSES)
    parts: list[list[tuple[float, float]]] = []
    con = sqlite3.connect(f"file:{ROADS_GPKG}?mode=ro", uri=True)
    for geom, highway in con.execute(
        "SELECT geom, highway FROM roads WHERE geom IS NOT NULL"
    ):
        if highway not in allowed:
            continue
        try:
            pts = _decode_gpkg_line(geom, struct)
        except Exception:  # noqa: BLE001 - one bad feature must not stop a build
            continue
        if pts and len(pts) >= 2:
            parts.append(pts)
    con.close()
    chains = stitch(parts)
    print(f"  {len(parts):,} ways -> {len(chains):,} chains, "
          f"{sum(len(c) for c in chains):,} vertices")
    return chains


def _decode_gpkg_line(blob: bytes, struct_mod) -> list[tuple[float, float]] | None:
    """Decode a GeoPackage LineString blob into [(lat, lon), ...]."""
    if not blob or blob[:2] != b"GP":
        return None
    flags = blob[3]
    order = "<" if flags & 0x01 else ">"
    # flags bits 1-3 encode the envelope: 0 none, 1 xy(32B), 2 xyz(48B), 3 xym,
    # 4 xyzm(64B).
    env_code = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env_code)
    if env_len is None:
        return None
    wkb = blob[8 + env_len:]
    if len(wkb) < 5:
        return None
    bo = "<" if wkb[0] == 1 else ">"
    if struct_mod.unpack(bo + "I", wkb[1:5])[0] % 1000 != 2:
        return None  # only LineString carries walkable/roadable geometry
    (n,) = struct_mod.unpack(bo + "I", wkb[5:9])
    return [
        struct_mod.unpack(bo + "dd", wkb[9 + i * 16: 25 + i * 16])
        for i in range(n)
    ]


def path_on_network(
    lines: list[list[tuple[float, float]]],
    cell_grid: dict[tuple[int, int], list[int]],
    cell_deg: float,
    a: tuple[float, float],
    b: tuple[float, float],
    snap_m: float = 400.0,
) -> list[tuple[float, float]] | None:
    """Slice of one network line between the two projections, or None.

    Both endpoints must project within `snap_m` of the line, and the caller must
    still check the result against MIN_PATH_RATIO -- two nearby stops can
    project onto adjacent vertices of the same dead-end, which yields a stub that
    is not a path between them.
    """
    gx, gy = int(a[0] / cell_deg), int(a[1] / cell_deg)
    hx, hy = int(b[0] / cell_deg), int(b[1] / cell_deg)
    cand: set[int] = set()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cand.update(cell_grid.get((gx + dx, gy + dy), ()))
            cand.update(cell_grid.get((hx + dx, hy + dy), ()))
    best: tuple[float, list, int, int] | None = None
    for ci in cand:
        line = lines[ci]
        ia, da = project(line, a)
        ib, db = project(line, b)
        if da > snap_m or db > snap_m:
            continue
        if best is None or da + db < best[0]:
            best = (da + db, line, ia, ib)
    if best is None:
        return None
    _, line, ia, ib = best
    lo, hi = (ia, ib) if ia <= ib else (ib, ia)
    if hi - lo < 1:
        return None
    return list(line[lo: hi + 1])


def build_grid(
    lines: list[list[tuple[float, float]]], cell_deg: float
) -> dict[tuple[int, int], list[int]]:
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for ci, line in enumerate(lines):
        for lat, lon in line:
            grid[(int(lat / cell_deg), int(lon / cell_deg))].append(ci)
    return grid


def project(
    line: list[tuple[float, float]], target: tuple[float, float]
) -> tuple[int, float]:
    """Nearest vertex on `line` to `target`: its index and the distance in metres.

    Equirectangular approximation about the target's latitude, which at the
    scale of one station-to-station hop (<= a few km) is accurate to well under
    a metre and far cheaper than a haversine per vertex.
    """
    cos_lat = math.cos(math.radians(target[0]))
    px, py = target[1] * cos_lat, target[0]
    best_i, best_d2 = 0, float("inf")
    for i, (lat, lon) in enumerate(line):
        d2 = (lon * cos_lat - px) ** 2 + (lat - py) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_i = i
    return best_i, math.sqrt(best_d2) * 111_000.0


def track_between(
    polylines: list[list[tuple[float, float]]],
    a: tuple[float, float],
    b: tuple[float, float],
) -> list[tuple[float, float]] | None:
    """The stretch of track between two stops, following the network order.

    Picks the polyline that passes closest to both stops, projects each stop
    onto it, and returns the slice in between -- so the line runs along the
    track instead of cutting across the country.

    Two guards matter, and both were needed after measuring:

      - the projections must be close to their stops, else the polyline merely
        passes somewhere nearby and the slice is meaningless
      - the slice must be no longer than the straight line times
        MAX_DETOUR_FACTOR, else the two projections landed at opposite ends of
        a country-spanning route. An earlier version returned 497 km for a
        4.2 km hop because it took the nearest point on the network to each
        stop and joined them across the whole network; every one of those was
        rejected as implausible and the segment fell back to a straight line.
    """
    best: tuple[float, list, int, int] | None = None
    for line in polylines:
        if len(line) < 2:
            continue
        ia, da = project(line, a)
        ib, db = project(line, b)
        # The stop must sit essentially on this polyline for the slice to mean
        # anything. 400 m absorbs station-node coordinate error in OSM.
        if da > 400 or db > 400:
            continue
        cost = da + db
        if best is None or cost < best[0]:
            best = (cost, line, ia, ib)

    if best is None:
        return None

    _, line, ia, ib = best
    lo, hi = (ia, ib) if ia <= ib else (ib, ia)
    if hi - lo < 1:
        return None
    return list(line[lo : hi + 1])


# ── OSRM: road geometry ────────────────────────────────────────────────────
# Raw OSRM responses cached on disk. The full build is ~1580 OSRM calls at
# roughly a third of a second each, so a rebuild costs minutes; with this cache
# a rebuild after a rule change (a tighter detour bound, endpoint snapping)
# re-reads the responses instead of re-fetching them. Stored separately from
# route_geometry.json because it is a fetch cache, not product data.
OSRM_RAW_CACHE = BASE / "data" / ".osrm_raw_cache.json"
_osrm_cache: dict[tuple[float, float, float, float], dict | None] = {}


def _load_osrm_cache() -> None:
    if not OSRM_RAW_CACHE.exists():
        return
    try:
        raw = json.loads(OSRM_RAW_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a corrupt cache just means re-fetching
        return
    for key, val in raw.items():
        parts = key.split(",")
        if len(parts) != 4:
            continue
        try:
            lat1, lon1, lat2, lon2 = (float(v) for v in parts)
        except ValueError:
            continue
        _osrm_cache[(lat1, lon1, lat2, lon2)] = val


def _save_osrm_cache() -> None:
    out = {
        ",".join(f"{v:.6f}" for v in key): val
        for key, val in _osrm_cache.items()
        if val is not None
    }
    OSRM_RAW_CACHE.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")


def osrm(a: dict, b: dict) -> dict | None:
    key = (a["lat"], a["lon"], b["lat"], b["lon"])
    if key in _osrm_cache:
        return _osrm_cache[key]
    url = (
        f"{OSRM_URL}/{a['lon']},{a['lat']};{b['lon']},{b['lat']}"
        "?overview=full&geometries=geojson"
    )
    out = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
        if data.get("code") == "Ok" and data.get("routes"):
            out = data["routes"][0]
    except Exception as exc:  # noqa: BLE001
        print(f"    osrm failed: {type(exc).__name__}", file=sys.stderr)
    _osrm_cache[key] = out
    return out


def simplify(points: list[tuple[float, float]], tol_m: float = 8.0) -> list[list[float]]:
    """Douglas-Peucker, to keep the committed cache small.

    The app draws at most a few hundred pixels of line, so sub-metre detail is
    wasted bytes in a file that is committed.
    """
    if len(points) < 3:
        return [[round(lat, 6), round(lon, 6)] for lat, lon in points]

    def rdp(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(pts) < 3:
            return pts
        (x1, y1), (x2, y2) = pts[0], pts[-1]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        max_d, index = 0.0, 0
        for i in range(1, len(pts) - 1):
            x, y = pts[i]
            if norm == 0:
                d = math.hypot(x - x1, y - y1)
            else:
                d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if d > max_d:
                max_d, index = d, i
        if max_d > tol_m / 111_000.0:
            return rdp(pts[: index + 1])[:-1] + rdp(pts[index:])
        return [pts[0], pts[-1]]

    return [[round(lat, 6), round(lon, 6)] for lat, lon in rdp(points)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only fetch N segments (smoke test)")
    ap.add_argument("--resume", action="store_true", help="keep existing entries")
    ap.add_argument("--force", action="store_true", help="rebuild from scratch")
    ap.add_argument(
        "--retry-rejected",
        action="store_true",
        help=(
            "re-evaluate only segments that already have a cache entry but were "
            "rejected (entry['reason'] set, no geometry). Uses the cached raw "
            "OSRM responses and the cached OSM rail network, so it needs no "
            "network for those and exists to apply a changed MAX_DETOUR_FACTOR "
            "to data already fetched."
        ),
    )
    args = ap.parse_args()

    _load_osrm_cache()
    seed = load_seed()
    stations = seed["stations"]
    segs = segments(stations, seed["lines"])
    print(f"seed: {len(stations)} stations, {len(seed['lines'])} lines, {len(segs)} distinct segments")

    existing: dict[str, dict] = {}
    if args.resume and OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("segments", {})
        print(f"resuming with {len(existing)} cached segments")

    if args.retry_rejected:
        # A rejected segment already has a key, so the "not in existing" filter
        # below would skip it forever and a rule change could never be applied
        # to data already fetched. Rebuild the todo list from the entries that
        # carry a reason instead.
        todo = [
            s
            for s in segs
            if f"{s[0]}|{s[1]}" in existing
            and not existing[f"{s[0]}|{s[1]}"].get("geometry")
            and existing[f"{s[0]}|{s[1]}"].get("reason")
        ]
        print(f"retry-rejected: {len(todo)} segments carry a rejection reason")
    else:
        todo = [s for s in segs if f"{s[0]}|{s[1]}" not in existing]
    total_missing = len(todo)
    if args.limit:
        todo = todo[: args.limit]
        if not args.force and not args.retry_rejected:
            # Refuse before spending the fetches, not after. This has already
            # gone wrong three times in one session: `--limit 40` over a
            # complete 1885-segment cache wrote 40 segments back with no
            # warning, and two mutation runs interrupted mid-flight left the
            # cache at 15 segments and the guard reverted away by
            # `git checkout`. Either way data/route_geometry.json -- the file
            # the map reads -- silently loses its geometry.
            print(
                f"\n!! --limit {args.limit} is a smoke test and will NOT write "
                f"{OUT_PATH.name}."
            )
            print(
                f"   A full build covers {len(segs)} segments; this run would "
                f"fetch only {len(todo)} of the {total_missing} missing."
            )
            print(
                "   The existing cache is left untouched. Pass --force to "
                "overwrite it anyway."
            )
            return 0
    print(f"to fetch: {len(todo)}")
    if not todo:
        print("nothing to do")
        return 0

    rail_segs = [s for s in todo if s[2] in ("train", "rail", "metro")]
    bus_segs = [s for s in todo if s[2] not in ("train", "rail", "metro")]
    print(f"  rail (OSM track): {len(rail_segs)}   bus (OSRM road): {len(bus_segs)}")

    polylines: list[list[tuple[float, float]]] = []
    if rail_segs:
        polylines = load_rail_network()

    # Local road network, used for any segment the cache has no answer for. It
    # is offline and deterministic, and a full build otherwise spends ~9 min in
    # OSRM requests.
    # Decoding the 232 MB GeoPackage and stitching it takes over ten minutes on
    # this machine, and it is not always needed: a segment whose raw OSRM
    # response is already cached can be re-derived with no network and no local
    # file at all. BLEDI_SKIP_ROADS=1 skips the decode when every remaining
    # segment can be answered from the OSRM cache, which turns a 15-minute run
    # into seconds. Set BLEDI_FORCE_ROADS=1 to always decode it regardless.
    road_lines: list[list[tuple[float, float]]] = []
    force_roads = os.environ.get("BLEDI_FORCE_ROADS", "").strip() not in ("", "0", "false")
    skip_roads = os.environ.get("BLEDI_SKIP_ROADS", "").strip() not in ("", "0", "false")
    if ROADS_GPKG and Path(ROADS_GPKG).exists() and (force_roads or not skip_roads):
        road_lines = load_road_network()
    elif skip_roads:
        print(
            "  BLEDI_SKIP_ROADS set: using cached OSRM responses only "
            "(segments the cache cannot answer stay straight)"
        )
    road_grid = build_grid(road_lines, 0.02) if road_lines else {}

    by_id = {s["id"]: s for s in stations if s.get("lat") and s.get("lon")}
    out: dict[str, dict] = dict(existing)
    stats: dict[str, int] = defaultdict(int)
    t0 = time.time()

    for i, (a_id, b_id, mode) in enumerate(todo, 1):
        a, b = by_id[a_id], by_id[b_id]
        straight = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        entry: dict = {"mode": mode, "source": None, "geometry": [], "reason": None}

        if mode in ("train", "rail", "metro") and polylines:
            track = track_between(polylines, (a["lat"], a["lon"]), (b["lat"], b["lon"]))
            if track and len(track) >= 2:
                length = sum(haversine(*p, *q) for p, q in zip(track, track[1:]))
                if straight > 0 and length <= straight * MAX_DETOUR_FACTOR:
                    entry["source"] = "osm-rail"
                    entry["geometry"] = simplify(track)
                else:
                    entry["reason"] = f"rail path {length:.0f} m implausible vs {straight:.0f} m straight"
            else:
                entry["reason"] = "no OSM rail track joins these stops"
        else:
            # Try the local network first: offline, deterministic, and it
            # resolves short urban hops OSRM detours around. OSRM remains the
            # fallback for anything the local file cannot snap to.
            coords: list[tuple[float, float]] = []
            if road_lines:
                local = path_on_network(
                    road_lines, road_grid, 0.02,
                    (a["lat"], a["lon"]), (b["lat"], b["lon"]),
                )
                if local:
                    local_len = sum(
                        haversine(*p_, *q_) for p_, q_ in zip(local, local[1:])
                    )
                    # Reject a stub. Two nearby stops can project onto adjacent
                    # vertices of one dead-end, giving a fragment that is not a
                    # route between them; the ratio is the only cheap way to see
                    # it, since a real path is never shorter than the crow
                    # flight.
                    if straight <= 1 or local_len >= straight * MIN_PATH_RATIO:
                        coords = local
                    else:
                        entry["reason"] = (
                            f"local path {local_len:.0f} m shorter than straight "
                            f"{straight:.0f} m"
                        )
            if not coords and not entry["reason"]:
                route = osrm(a, b)
                coords = (
                    [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
                    if route
                    else []
                )
            length = (
                sum(haversine(*p_, *q_) for p_, q_ in zip(coords, coords[1:]))
                if len(coords) >= 2
                else 0.0
            )
            # Road/bus uses the looser bound: a bus on a one-way grid really
            # does drive ~3x the crow-flies distance between two stops, and
            # rejecting those left 250+ legs drawn as straight lines. Anything
            # past MAX_DETOUR_FACTOR_ROAD is still dropped as a mapping error.
            if coords and straight > 0 and length <= straight * MAX_DETOUR_FACTOR_ROAD:
                entry["source"] = "osrm-driving"
                entry["geometry"] = simplify(coords)
            elif not coords:
                entry["reason"] = "OSRM returned no route"
            else:
                entry["reason"] = (
                    f"road path {length:.0f} m implausible vs {straight:.0f} m straight"
                )

        if entry["geometry"]:
            # Snap the endpoints onto the station coordinates.
            #
            # OSM returns the nearest *track vertex*, which for most stations is
            # tens of metres from the station node itself (Sousse Bab Jdid:
            # 35.823005/10.641466 vs the stop's 35.823063/10.6415928). The
            # frontend's path getter requires a geometry to begin and end
            # exactly on the step endpoints or it discards it, so unsnapped
            # geometry was correct data that the client threw away.
            entry["geometry"][0] = [a["lat"], a["lon"]]
            entry["geometry"][-1] = [b["lat"], b["lon"]]
            stats[entry["source"]] += 1
        else:
            stats["missing"] += 1
        out[f"{a_id}|{b_id}"] = entry

        if i % 25 == 0 or i == len(todo):
            rate = i / max(1e-9, time.time() - t0)
            left = (len(todo) - i) / rate if rate else 0
            print(
                f"  {i}/{len(todo)}  ok={stats.get('osm-rail', 0) + stats.get('osrm-driving', 0)}"
                f"  missing={stats['missing']}  {rate:.1f}/s  ~{left / 60:.1f} min left",
                flush=True,
            )

    payload = {
        "metadata": {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "seed": SEED_PATH.name,
            "segments": len(out),
            "resolved": sum(1 for v in out.values() if v["geometry"]),
            "missing": sum(1 for v in out.values() if not v["geometry"]),
            "rail_source": "OSM route relations (type=route, route=rail|train|light_rail|tram|monorail)",
            "bus_source": "OSRM driving profile",
            "walk_legs": "not fetched: footways absent from the driving profile and walk legs are <= 900 m",
            "simplify_tolerance_m": 8.0,
        },
        "segments": out,
    }
    OUT_PATH.write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    _save_osrm_cache()
    size_mb = OUT_PATH.stat().st_size / 1e6
    print(f"\nwrote {OUT_PATH.name}: {len(out)} segments, {size_mb:.2f} MB")
    print(f"  resolved {payload['metadata']['resolved']}, missing {payload['metadata']['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
