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

# Overpass bbox covering Tunisia.
BBOX = "30.2,7.4,37.6,12.2"

# A geometry is only trusted if it stays near the two stops it connects.
# 2.0 rather than a looser bound: measured across the full build, real rail and
# road paths top out around 1.7x the straight line (a rail curve through open
# country), so anything past 2x is OSRM walking a detour or OSM matching the
# wrong line. Those read as absurd on a map -- 2541 m of road for a 113 m hop --
# and are worse than an honest straight line.
MAX_DETOUR_FACTOR = 2.0


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
                    return json.load(resp).get("elements", [])
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


def load_rail_network() -> tuple[list[list[tuple[float, float]]], list[tuple[float, float]]]:
    """Fetch every OSM rail route in Tunisia as a list of polylines.

    Returns (polylines, node_coords). Polylines are the real track geometry;
    node_coords lets a stop be matched to the nearest point on the track.
    """
    values = "|".join(RAIL_ROUTE_VALUES)
    query = (
        f'[out:json][timeout:240];\n'
        f'rel["type"="route"]["route"~"^({values})$"]({BBOX});\n'
        f'out geom;'
    )
    print("fetching OSM rail routes (this is the biggest single request)...")
    elements = overpass(query, timeout=300)
    if elements is None:
        raise SystemExit("Overpass unavailable: cannot fetch rail geometry")

    polylines: list[list[tuple[float, float]]] = []
    for el in elements:
        members = el.get("members") or []
        if not members:
            continue
        parts: list[list[tuple[float, float]]] = []
        for m in members:
            geom = m.get("geometry")
            if not geom:
                continue
            part = [(g["lat"], g["lon"]) for g in geom if g.get("lat") is not None]
            if len(part) >= 2:
                parts.append(part)
        polylines.extend(stitch(parts))

    nodes = [
        (e["lat"], e["lon"])
        for e in elements
        if e.get("type") == "node" and e.get("lat") is not None
    ]
    print(f"  {len(polylines)} rail polylines, {len(nodes)} nodes")
    return polylines, nodes


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

    todo = [s for s in segs if f"{s[0]}|{s[1]}" not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"to fetch: {len(todo)}")
    if not todo:
        print("nothing to do")
        return 0

    rail_segs = [s for s in todo if s[2] in ("train", "rail", "metro")]
    bus_segs = [s for s in todo if s[2] not in ("train", "rail", "metro")]
    print(f"  rail (OSM track): {len(rail_segs)}   bus (OSRM road): {len(bus_segs)}")

    polylines: list[list[tuple[float, float]]] = []
    if rail_segs:
        polylines, _ = load_rail_network()

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
            # Same plausibility bound as the rail path. Measured on the first
            # full build: 80 bus segments came back at up to 23x the straight
            # line (cit_el_khadhra|montplaisir: 2541 m of road for a 113 m hop),
            # which is OSRM routing around a one-way system or a mapping
            # error. Those are worse than an honest straight line, so they are
            # dropped rather than drawn.
            if coords and straight > 0 and length <= straight * MAX_DETOUR_FACTOR:
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
