#!/usr/bin/env python3
"""
BLEDI.TN — Tunisia Transport API
FastAPI backend with embedded seed data + local Dijkstra router.

Run: uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000
Or, from repo root: python -m uvicorn src.backend.app.main:app --host 127.0.0.1 --port 8000

Data provenance: see docs/provenance.md. Most routing data is derived from
Tunismapper; the /api/v1/itinerary tunismapper proxy is disabled by default.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Local transit router (physical-cost Dijkstra).
from src.backend.app.routing import (
    COMBINATIONS,
    FAMILIES,
    OPTION_MODES,
    USER_MODES,
    Router,
    canonical_mode,
    label_for,
    label_modes_fr,
    mode_label_fr,
    modes_for,
)

log = logging.getLogger("bledi")

# ── Paths ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[3]  # repo root
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"
# Real route geometry, precomputed by tool/build_route_geometry.py. Without it
# every leg is drawn as a straight line between two stops; the seed carries no
# shape data at all (0 of 232 lines have one), so this is the only way the map
# can follow an actual track or road. Optional: absent means straight lines.
GEOMETRY_PATH = BASE / "data" / "route_geometry.json"

# Prefer the tagged file if it exists, else fall back to the original.
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# Physical track geometry (rail / metro alignments from OSM relations, road
# alignments from OSRM) keyed by "<stop_a>|<stop_b>". Built by
# scripts/build_route_geometry.py and committed, so the network layer has real
# track to draw instead of straight lines between stops.
_ROUTE_GEOMETRY_PATH = BASE / "data" / "route_geometry.json"

# Rail and road alignments for the map's base layers. Built by
# tool/build_map_overlays.py from the official Overpass exports in
# Downloads/tunisia-transport-data (rail-network-exports, highways). Kept
# separate from route_geometry.json because these are the PHYSICAL network --
# every rail line and every motorway/trunk/primary road in the country -- not
# per-route shape for a specific service.
_MAP_RAIL_PATH = BASE / "data" / "map_rail.geojson"
_MAP_ROADS_PATH = BASE / "data" / "map_roads.geojson"

# Louage station connections, resolved from each national louage station's
# destinations_served against the station list. Built by
# tool/build_station_index.py. Unresolved destinations are listed in the file
# rather than guessed, so the client can show what is genuinely unknown.
_LOUAGE_LINKS_PATH = BASE / "data" / "louage_links.json"

# ── Config ──────────────────────────────────────────────────────────────
OSRM_URL = os.environ.get(
    "OSRM_URL",
    "https://router.project-osrm.org/route/v1/driving",
)
OSRM_TIMEOUT = int(os.environ.get("OSRM_TIMEOUT", "30"))
# Local dev origins only. 8080 is the Flutter web dev server's default port
# (see src/mobile/tool/serve_web.py); without it a browser build gets a CORS
# failure instead of data. Override with ALLOWED_ORIGINS for other hosts.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        ",".join([
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]),
    ).split(",")
    if o.strip()
]
ENABLE_TUNISMAPPER_PROXY = os.environ.get("ENABLE_TUNISMAPPER_PROXY", "").strip().lower() in (
    "1", "true", "yes",
)

# ── CORS ────────────────────────────────────────────────────────────────
# Do NOT combine wildcard origins with allow_credentials=True.
app = FastAPI(
    title="bledi.tn",
    description="Tunisia public transport routing API",
    version="0.2.0",
)
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
        allow_credentials=False,
    )
else:
    # Fallback: allow the frontend origin only if nothing is configured.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
        allow_credentials=False,
    )


# ── Seed loading ────────────────────────────────────────────────────────
with _SEED_PATH.open(encoding="utf-8") as _f:
    SEED_DATA: dict[str, Any] = json.load(_f)

_stations: list[dict[str, Any]] = SEED_DATA.get("stations", [])
_lines: list[dict[str, Any]] = SEED_DATA.get("lines", [])

# Geometry cache: "a|b" -> {"geometry": [[lat, lon], ...], "source": ...}.
# Keyed by an unordered station-id pair so it is direction-independent.
_GEOMETRY: dict[str, dict[str, Any]] = {}
if GEOMETRY_PATH.exists():
    with GEOMETRY_PATH.open(encoding="utf-8") as _f:
        _GEOMETRY = json.load(_f).get("segments", {})
    log.info(
        "Loaded route geometry: %d segments (%d with geometry) from %s",
        len(_GEOMETRY),
        sum(1 for v in _GEOMETRY.values() if v.get("geometry")),
        GEOMETRY_PATH.name,
    )
else:
    log.info(
        "No route geometry cache at %s; legs will render as straight lines. "
        "Run: python src/backend/tool/build_route_geometry.py",
        GEOMETRY_PATH.name,
    )


def _geometry_for(from_id: str | None, to_id: str | None) -> list[list[float]]:
    """Cached geometry between two stations, oriented along travel direction.

    The cache key is the unordered pair min|max and the stored polyline always
    runs min -> max. A step runs from_id -> to_id, so when from_id sorts after
    to_id the polyline has to be reversed to keep the drawn line pointing the
    way the rider travels. Returns [] when there is no geometry, which tells
    the client to draw the straight line instead.
    """
    if not from_id or not to_id:
        return []
    entry = _GEOMETRY.get(f"{min(from_id, to_id)}|{max(from_id, to_id)}")
    if not entry or not entry.get("geometry"):
        return []
    pts = entry["geometry"]
    return list(reversed(pts)) if from_id > to_id else list(pts)

# ── City (governorate) assignment ──────────────────────────────────────────
# The seed has no governorate field, so each station is assigned to its nearest
# governorate seat. Measured on the seed: 1 711 stations -> 21 groups with no
# runaway cluster, and only 18 stations fall further than 60 km from any seat
# (remote villages like Sened and Maknassy). Those get [UNASSIGNED_CITY] rather
# than being forced into a wrong governorate.
#
# Reference points are the 24 governorate seats.
CITY_SEATS: list[tuple[str, float, float]] = [
    ("Tunis", 36.8065, 10.1815),
    ("Ariana", 36.8628, 10.1957),
    ("Ben Arous", 36.7520, 10.2220),
    ("Manouba", 36.8161, 10.1011),
    ("Nabeul", 36.4560, 10.7376),
    ("Zaghouan", 36.4028, 10.1425),
    ("Bizerte", 37.2744, 9.8739),
    ("Béja", 36.7256, 9.1817),
    ("Jendouba", 36.5008, 8.7806),
    ("Le Kef", 36.1742, 8.7147),
    ("Siliana", 36.3667, 9.2167),
    ("Kairouan", 35.6781, 10.0963),
    ("Kassab", 35.1833, 8.8000),
    ("Sidi Bouzid", 36.4044, 9.4844),
    ("Sousse", 35.8256, 10.6360),
    ("Monastir", 35.7777, 10.8263),
    ("Mahdia", 35.5047, 11.0622),
    ("Sfax", 34.7406, 10.7603),
    ("Kébili", 33.8814, 8.8742),
    ("Gabès", 33.8815, 10.0982),
    ("Médenine", 33.3547, 10.5052),
    ("Tataouine", 32.9291, 10.4517),
    ("Ghorbel", 34.7484, 10.7369),
    ("Tozeur", 33.9197, 8.1339),
]

# Beyond this distance from every seat a station is left unassigned.
MAX_CITY_DISTANCE_KM = 60.0

# Bucket for stations too remote to belong to any governorate. Assigned
# explicitly rather than left null so clients never have to invent a fallback.
UNASSIGNED_CITY = "Other"

_EARTH_R_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * _EARTH_R_KM * math.asin(math.sqrt(a))


def _simplify_path(pts: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker on [[lat, lon]] pairs.

    Long OSRM polylines are hundreds of vertices for a shape that reads the
    same at city zoom. Simplifying server-side keeps the network payload small
    without changing the drawn line, and the tolerance is a request parameter
    so a client that needs full fidelity can ask for `simplify=0`.
    """
    if len(pts) < 3 or tol <= 0:
        return pts

    arr = np.asarray(pts, dtype="float64")
    keep = np.zeros(len(arr), dtype=bool)
    keep[0] = keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(arr) - 1)]

    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = arr[i], arr[j]
        seg = b - a
        seg_len = float(np.hypot(seg[0], seg[1]))
        chunk = arr[i + 1 : j]
        if seg_len == 0:
            d = np.hypot(chunk[:, 0] - a[0], chunk[:, 1] - a[1])
        else:
            # Perpendicular distance to the chord (degrees; the tolerance is
            # in degrees too, so no metric conversion is needed).
            d = np.abs(
                seg[1] * (chunk[:, 0] - a[0]) - seg[0] * (chunk[:, 1] - a[1])
            ) / seg_len
        k = int(np.argmax(d))
        if float(d[k]) > tol:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))

    return [pts[i] for i in range(len(pts)) if keep[i]]


def nearest_city(lat: float, lon: float) -> str:
    """Nearest governorate seat, or [UNASSIGNED_CITY] if too remote.

    Always returns a value: callers get a stable string key rather than having
    to handle None. The 18 stations beyond [MAX_CITY_DISTANCE_KM] fall into
    [UNASSIGNED_CITY] instead of being forced into a wrong governorate.
    """
    best_name: str = UNASSIGNED_CITY
    best_d = MAX_CITY_DISTANCE_KM
    for name, slat, slon in CITY_SEATS:
        d = _haversine_km(lat, lon, slat, slon)
        if d < best_d:
            best_d, best_name = d, name
    return best_name


# Louage / taxi stops come from separate seed files that the main transit seed
# does not contain. Their modes are louage_red / louage_blue / louage_green /
# taxi, and they are marked with `source="louage"` so the client can colour and
# filter them distinctly.
LOUAGE_SEED_PATH = BASE / "data" / "seed_routes_destination_tunis.json"
_LOUAGE_STATIONS: list[dict[str, Any]] = []
_LOUAGE_LINES: list[dict[str, Any]] = []
if LOUAGE_SEED_PATH.exists():
    with LOUAGE_SEED_PATH.open(encoding="utf-8") as _f:
        _louage = json.load(_f)
    _LOUAGE_STATIONS = _louage.get("stations", [])
    _LOUAGE_LINES = _louage.get("routes", [])
    log.info(
        "Loaded louage/taxi seed: %d stops, %d routes from %s",
        len(_LOUAGE_STATIONS), len(_LOUAGE_LINES), LOUAGE_SEED_PATH.name,
    )

# Route ids from the louage seed, so a station can advertise its services.
_LOUAGE_ROUTES_BY_STOP: dict[str, list[dict[str, Any]]] = defaultdict(list)
for _r in _LOUAGE_LINES:
    for _endpoint in (_r.get("from"), _r.get("to")):
        if _endpoint:
            _LOUAGE_ROUTES_BY_STOP[_endpoint].append(_r)

# Id -> station / line index for O(1) lookups (replaces O(lines*stations) scans).
STATION_BY_ID: dict[str, dict[str, Any]] = {}
for _s in _stations:
    _sid = _s.get("id")
    if _sid:
        STATION_BY_ID[_sid] = _s


# ── Mode normalisation for station features ────────────────────────────────
# The seed keeps raw provenance tags in `mode` (rail, louage_red, unknown...).
# Those are meaningful in the seed but they are NOT selectable modes: the UI
# filter and the neon network palette both key off the canonical vocabulary.
# The seed's own audit records why the odd tags exist:
#   * unknown_mode_resolution -> 76 stops whose operator export carried no mode
#     at all (kiosks, roundabouts, school stops). They are still real, geocoded
#     points, so they stay on the map -- as "unclassified", never as a
#     scheduled bus, which is what the old "unknown -> bus" default did.
#   * `rail` is a Transtu suburban-rail stop: same family as train.
#   * louage_red|blue|green are colour-coded louage terminals: all louage.
# Mode tags that reach the API as "unknown"/"rail"/"louage_*" are therefore
# canonicalised here so a client never has to re-derive the mapping.
_UNCLASSIFIED = "unclassified"

# Station-level extra tags the UI understands but that are not routable modes.
_STATION_ONLY_MODES: dict[str, frozenset[str]] = {
    _UNCLASSIFIED: frozenset({"unknown", "unclassified", ""}),
}


def station_modes(s: dict[str, Any]) -> list[str]:
    """Canonical, de-duplicated modes for a station row.

    Returns the rider-facing categories the stop actually serves, in
    USER_MODES display order, with `unclassified` last. A stop tagged
    `rail` yields `["train"]`; one tagged `louage_red` yields `["louaj"]`;
    an untagged sweep stop yields `["unclassified"]`.
    """
    raw: list[str] = []
    primary = s.get("mode")
    if primary:
        raw.append(str(primary))
    for extra in s.get("modes") or []:
        if extra:
            raw.append(str(extra))

    seen: set[str] = set()
    for r in raw:
        rl = r.strip().lower()
        if not rl:
            continue
        for station_only, aliases in _STATION_ONLY_MODES.items():
            if rl in aliases:
                seen.add(station_only)
                break
        else:
            seen.add(canonical_mode(rl))

    ordered = [m for m in USER_MODES if m in seen]
    if _UNCLASSIFIED in seen:
        ordered.append(_UNCLASSIFIED)
    return ordered


def primary_station_mode(s: dict[str, Any]) -> str:
    """The single mode used to colour a station dot.

    Prefers a routable mode over `unclassified` so a stop that is served by
    real lines is never painted as an unclassified point.
    """
    modes = station_modes(s)
    for m in modes:
        if m != _UNCLASSIFIED:
            return m
    return modes[0] if modes else _UNCLASSIFIED

LINE_BY_ID: dict[str, dict[str, Any]] = {}
# Also index by number for the /lines/{line_number} endpoint (number is not unique).
LINES_BY_NUMBER: dict[str, list[dict[str, Any]]] = defaultdict(list)
for _ln in _lines:
    _lid = _ln.get("id")
    if _lid:
        LINE_BY_ID[_lid] = _ln
    _num = str(_ln.get("number") or _ln.get("route_id") or "")
    if _num:
        LINES_BY_NUMBER[_num].append(_ln)

log.info(
    "Loaded seed: %d stations, %d lines from %s",
    len(_stations), len(_lines), _SEED_PATH.name,
)


# ── Local transit router instance ──────────────────────────────────────────
# Built once at startup from the already-loaded seed (STATION_BY_ID + _lines).
# Reused by the /api/v1/route/transit endpoint — no re-load per request.
ROUTER: Router = Router(STATION_BY_ID, _lines)


# ── Pydantic response models ─────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"
    service: str = "bledi.tn"
    seed_file: str = _SEED_PATH.name
    stations_count: int = len(_stations)
    lines_count: int = len(_lines)


class StationGeoJSON(BaseModel):
    type: str = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class StationsMeta(BaseModel):
    count: int
    total: int
    # Canonical mode -> number of features serving it. Lets the client show a
    # real inventory per mode without counting the feature list itself.
    by_mode: dict[str, int] = Field(default_factory=dict)


class StationsResponse(BaseModel):
    type: str = "FeatureCollection"
    features: list[StationGeoJSON]
    metadata: StationsMeta


class CitySummary(BaseModel):
    """A city/governorate with its station inventory."""

    name: str
    lat: float
    lon: float
    station_count: int
    by_mode: dict[str, int] = Field(default_factory=dict)


class CityListResponse(BaseModel):
    cities: list[CitySummary]
    count: int


class NearStation(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    dist_m: float
    lines: list[Any] = Field(default_factory=list)


class NearResponse(BaseModel):
    near: list[NearStation]
    query: dict[str, float]


class LineSummary(BaseModel):
    id: str
    number: str | None = None
    short_name: str | None = None
    long_name: str | None = None
    mode: str = "bus"
    color: str | None = None
    route_id: str | None = None
    stops_count: int = 0


class LinesResponse(BaseModel):
    lines: list[LineSummary]
    count: int


class StopInfo(BaseModel):
    stop_id: str | None = None
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    order: int | None = None
    schedule: list[str] | None = None
    lines: list[Any] | None = None


class LineDetail(BaseModel):
    line: dict[str, Any]
    stops: list[StopInfo]
    count: int
    # ── B4 additions: geometry honesty ────────────────────────────────
    mode: str | None = None
    mode_label: str | None = None
    geometry: dict[str, Any] | None = None      # GeoJSON LineString, [[lon,lat]]
    geometry_complete: bool = False
    geometry_segments: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []


# ── Pydantic models for the local transit-router endpoint ─────────────────
#
# Step shape is deliberately the same arrays the frontend computeTransit()
# renderer reads (step.start[0]/[1], step.end[0]/[1]) so the existing safe-DOM
# map plotter needs no new code path.
class TransitStep(BaseModel):
    type: str                     # walk | ride | transfer | taxi
    start: list[float]            # [lat, lon]
    end: list[float]              # [lat, lon]
    color: str | None = None
    stop_name: str | None = None
    duration_min: float = 0.0
    mode: str | None = None
    line: str | None = None
    from_name: str | None = None
    to_name: str | None = None


class TransitOption(BaseModel):
    duration: float               # total seconds
    duration_min: float
    transfers: int = 0
    has_walk_transfer: bool = False
    steps: list[TransitStep] = Field(default_factory=list)
    fare_dinars: float | None = None


class TransitResponse(BaseModel):
    best_fastest: TransitOption | None = None
    best_less_walk: TransitOption | None = None
    alternatives: list[TransitOption] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── OSRM / Nominatim via backend with TTL cache + User-Agent ─────────────
class _TTLCache:
    """Tiny in-memory TTL cache for OSRM/Nominatim responses."""

    def __init__(self, ttl_s: float = 300.0) -> None:
        self._ttl = ttl_s
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.time()
        val = self._store.get(key)
        if val is None:
            return None
        ts, payload = val
        if now - ts > self._ttl:
            del self._store[key]
            return None
        return payload

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)


_osrm_cache = _TTLCache(ttl_s=600.0)
_nominatim_cache = _TTLCache(ttl_s=3600.0)
_OSM_UA = "bledi.tn/0.2.0 (transport routing; contact: maintainer@bledi.tn)"


def query_osrm(start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any] | None:
    key = f"{start[0]:.6f},{start[1]:.6f}|{end[0]:.6f},{end[1]:.6f}"
    cached = _osrm_cache.get(key)
    if cached is not None:
        return cached
    url = f"{OSRM_URL}/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _OSM_UA})
        with urllib.request.urlopen(req, timeout=OSRM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            _osrm_cache.set(key, data)
            return data
    except Exception as exc:
        log.warning("OSRM unreachable at %s: %s", OSRM_URL, exc)
        return None


def query_nominatim(query: str) -> list[dict[str, Any]] | None:
    key = query.strip().lower()
    cached = _nominatim_cache.get(key)
    if cached is not None:
        return cached
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={urllib.parse.quote(query)}&countrycodes=tn&limit=3&format=json"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _OSM_UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            _nominatim_cache.set(key, data)
            return data
    except Exception as exc:
        log.warning("Nominatim unreachable: %s", exc)
        return None


# ── Endpoints ────────────────────────────────────────────────────────────
@app.get("/api/v1/health", tags=["System"])
def health_check() -> HealthResponse:
    """Health check + seed summary."""
    return HealthResponse()


@app.get("/api/v1/", tags=["System"])
def root() -> dict[str, Any]:
    return {
        "service": "bledi.tn",
        "version": "0.2.0",
        "description": "Tunisia public transport routing",
        "docs": "/docs",
        "endpoints": {
            "stations": "/api/v1/stations",
            "stations/near": "/api/v1/stations/near",
            "lines": "/api/v1/lines",
            "lines-by-number": "/api/v1/lines/{line_number}",
            "route": "/api/v1/route",
            "itinerary": "/api/v1/itinerary",
            "geocode": "/api/v1/geocode",
        },
    }


@app.get("/api/v1/stations", response_model=StationsResponse, tags=["Stations"])
def list_stations() -> StationsResponse:
    """All stations as a GeoJSON FeatureCollection (GPS-only).

    Properties include the seed's real `mode` / `operator` / `route_type` plus
    a derived `city` (nearest governorate seat), so a client can colour and
    filter stops by transport mode without re-deriving anything.

    Louage/taxi stops from the secondary seed are merged in with
    `source="louage"` and their own modes; they are appended after the transit
    stations so existing ids and ordering are unchanged.
    """
    features: list[StationGeoJSON] = []
    missing_coords: int = 0
    for s in _stations:
        lat, lon = s.get("lat"), s.get("lon")
        if not lat or not lon or lat == 0 or lon == 0:
            missing_coords += 1
            log.warning("Station %s has no/zero coordinates: %s", s.get("id"), s.get("name"))
            continue
        modes = station_modes(s)
        features.append(
            StationGeoJSON(
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties={
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "name_en": s.get("name_en"),
                    # Canonical rider-facing mode: what the client colours and
                    # filters by. `mode_raw` keeps the seed tag for audit.
                    "mode": primary_station_mode(s),
                    "modes": modes,
                    "mode_raw": s.get("mode"),
                    "operator": s.get("operator"),
                    "route_type": s.get("route_type"),
                    "license_status": s.get("license_status"),
                    "city": nearest_city(lat, lon),
                    "source": s.get("source"),
                    "lines": s.get("lines_served", []),
                },
            )
        )

    # Louage / taxi hubs, keyed to avoid id collisions with transit stations.
    for s in _LOUAGE_STATIONS:
        loc = s.get("location") or {}
        lat, lon = loc.get("lat"), loc.get("lon")
        if not lat or not lon:
            continue
        routes = _LOUAGE_ROUTES_BY_STOP.get(s.get("id", ""), [])
        raw_modes = sorted({r.get("mode") for r in routes if r.get("mode")})
        # Every louage colour variant collapses onto the single louage mode.
        canon = sorted({canonical_mode(m) for m in raw_modes}) or ["louaj"]
        lines_served: list[dict[str, Any]] = [
            {
                "route_short_name": r.get("mode"),
                "route_color": None,
                "direction": f"{r.get('from')} → {r.get('to')}",
                "route_id": r.get("from"),
            }
            for r in routes
        ]
        features.append(
            StationGeoJSON(
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties={
                    "id": f"louage_{s.get('id')}",
                    "name": s.get("name_fr") or s.get("name_en") or s.get("id"),
                    "name_en": s.get("name_en"),
                    # A stop can serve several louage colours; report them all
                    # and let the client treat any of them as the louage mode.
                    "mode": canon[0],
                    "modes": canon,
                    "mode_raw": raw_modes[0] if len(raw_modes) == 1 else "louage",
                    "operator": "Louage",
                    "route_type": s.get("type"),
                    "license_status": "unknown-third-party",
                    # The seed carries a real governorate for these stops.
                    "city": s.get("governorate") or nearest_city(lat, lon),
                    "source": "louage",
                    "fare_display": s.get("fare_display"),
                    "lines": lines_served,
                },
            )
        )

    # Per-mode tallies so a client can show real inventory without counting.
    by_mode: dict[str, int] = defaultdict(int)
    for f in features:
        for m in f.properties.get("modes") or [f.properties.get("mode")]:
            if m:
                by_mode[m] += 1

    return StationsResponse(
        features=features,
        metadata=StationsMeta(
            count=len(features),
            total=len(_stations),
            by_mode=dict(sorted(by_mode.items(), key=lambda kv: -kv[1])),
        ),
    )


@app.get("/api/v1/network", tags=["Network"])
def network_geometry(
    modes: str | None = Query(
        None,
        description="Comma-separated modes to include (default: all track modes)",
    ),
    bbox: str | None = Query(
        None,
        description="min_lon,min_lat,max_lon,max_lat — only return segments overlapping it",
    ),
    simplify: float = Query(
        0.0,
        ge=0.0,
        le=0.01,
        description="Douglas-Peucker tolerance in degrees (0 = no simplification)",
    ),
) -> dict[str, Any]:
    """Physical track geometry for the network, keyed by transport mode.

    This is what the map draws underneath the stops: rail and metro alignments
    traced from OSM route relations, and the road alignments the bus and louage
    lines actually follow. Each segment carries `mode` plus `source`, so a
    client can paint rail and road differently instead of inferring track type
    from a stop colour.

    Honesty contract (same as /lines/{id}): a segment with no cached geometry
    is NOT stitched into a straight line across the country. It is returned
    with `has_geometry: false` and a `gap_m` so the client can dash it or drop
    it. `metadata.missing` counts them.

    Geometry is returned as [[lat, lon]] pairs — Leaflet's native order, which
    is also how the routing legs are already delivered, so the client has one
    coordinate convention rather than two.
    """
    wanted: set[str] | None = None
    if modes:
        wanted = set()
        for raw in modes.split(","):
            m = raw.strip().lower()
            if m:
                wanted.add(canonical_mode(m))
        if not wanted:
            wanted = None

    box: tuple[float, float, float, float] | None = None
    if bbox:
        parts = bbox.split(",")
        if len(parts) != 4:
            raise HTTPException(
                status_code=400,
                detail="bbox must be min_lon,min_lat,max_lon,max_lat",
            )
        try:
            box = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bbox values must be numbers") from exc

    if not _ROUTE_GEOMETRY_PATH.exists():
        return JSONResponse(
            {
                "error": "network geometry not built",
                "detail": f"{_ROUTE_GEOMETRY_PATH.name} is missing; run scripts/build_route_geometry.py",
                "segments": [],
            },
            status_code=503,
        )

    with _ROUTE_GEOMETRY_PATH.open(encoding="utf-8") as fh:
        raw_segments = json.load(fh).get("segments", {})

    out: list[dict[str, Any]] = []
    by_mode: dict[str, int] = defaultdict(int)
    missing = 0
    min_lon, min_lat, max_lon, max_lat = box if box is not None else (0.0, 0.0, 0.0, 0.0)

    def _in_box(la: float, lo: float) -> bool:
        return box is None or (min_lat <= la <= max_lat and min_lon <= lo <= max_lon)

    for key, seg in raw_segments.items():
        seg_mode = canonical_mode(seg.get("mode"))
        if wanted is not None and seg_mode not in wanted:
            continue
        pts = seg.get("geometry") or []
        if simplify > 0 and len(pts) > 2:
            pts = _simplify_path(pts, simplify)
        if len(pts) < 2:
            # Reported, not stitched: the client must know a link exists but
            # has no traced track, so it can dash it rather than draw a
            # straight line across the country. Bbox still applies, via the
            # endpoints, or a city view would drag in every gap in the network.
            a, b = key.split("|", 1) if "|" in key else (key, "")
            pa = STATION_BY_ID.get(a) or {}
            pb = STATION_BY_ID.get(b) or {}
            if not (pa.get("lat") and pb.get("lat")):
                continue
            if not (_in_box(pa["lat"], pa["lon"]) or _in_box(pb["lat"], pb["lon"])):
                continue
            missing += 1
            out.append(
                {
                    "id": key,
                    "mode": seg_mode,
                    "source": seg.get("source"),
                    "has_geometry": False,
                    "geometry": [],
                    "from_stop_id": a,
                    "to_stop_id": b,
                    "straight_m": round(
                        _haversine_km(pa["lat"], pa["lon"], pb["lat"], pb["lon"]) * 1000.0
                    ),
                }
            )
            continue

        if not any(_in_box(la, lo) for la, lo in pts):
            continue

        by_mode[seg_mode] += 1
        out.append(
            {
                "id": key,
                "mode": seg_mode,
                "source": seg.get("source"),
                "has_geometry": True,
                "geometry": pts,
            }
        )

    return {
        "segments": out,
        "metadata": {
            "count": len(out),
            "by_mode": dict(sorted(by_mode.items(), key=lambda kv: -kv[1])),
            "missing_geometry": missing,
            "available_modes": sorted(by_mode),
        },
    }


def _load_overlay(path: Path, kind: str) -> dict[str, Any]:
    """Load a built GeoJSON overlay, or explain honestly why it is absent.

    Returns the features in Leaflet order ([lat, lon]) with the properties the
    client needs. A missing file is reported as 503 with the build command
    rather than served as an empty layer, because an empty layer looks like
    "Tunisia has no railways" instead of "the overlay was never built".
    """
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(f"{path.name} is missing; run "
                    f"`python tool/build_map_overlays.py` to build it from "
                    f"Downloads/tunisia-transport-data"),
        )
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    feats: list[dict[str, Any]] = []
    for f in data.get("features", []):
        geom = f.get("geometry") or {}
        if geom.get("type") != "LineString":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        feats.append({
            "kind": kind,
            "properties": f.get("properties") or {},
            # GeoJSON is [lon, lat]; Leaflet wants [lat, lon]. Converted here so
            # the client has one convention (the same one /network uses).
            "geometry": [[c[1], c[0]] for c in coords],
        })
    return {
        "features": feats,
        "metadata": {**(data.get("metadata") or {}), "returned": len(feats)},
    }


@app.get("/api/v1/map/rail", tags=["Network"])
def map_rail() -> dict[str, Any]:
    """Every passenger rail and light-rail alignment in Tunisia.

    Drawn as the map's rail base layer. `properties.mode` is `train` or `metro`
    so the client can style them apart; `ref`/`name` carry the line identity
    where OSM records one. Disused, abandoned, yard, spur and siding track is
    excluded at build time -- it is not a passenger route.
    """
    return _load_overlay(_MAP_RAIL_PATH, "rail")


@app.get("/api/v1/map/roads", tags=["Network"])
def map_roads() -> dict[str, Any]:
    """The intercity road network: motorway, trunk and primary only.

    `properties.highway` is the road class and `ref` the road number (RN1, A1,
    …), which is what a rider recognises. Secondary and tertiary roads are
    omitted as visual noise. Simplified at build time to ~16 m.
    """
    return _load_overlay(_MAP_ROADS_PATH, "road")


@app.get("/api/v1/map/overlays", tags=["Network"])
def map_overlays() -> dict[str, Any]:
    """Rail and roads in one response, for a client that wants both at once.

    Either layer may be independently absent; when it is, its entry carries an
    `error` string instead of features, so one missing overlay does not blank
    the other.
    """
    out: dict[str, Any] = {}
    for name, path, kind in (("rail", _MAP_RAIL_PATH, "rail"),
                             ("roads", _MAP_ROADS_PATH, "road")):
        try:
            out[name] = _load_overlay(path, kind)
        except HTTPException as exc:
            out[name] = {"features": [], "error": str(exc.detail)}
    return out


@app.get("/api/v1/louage/links", tags=["Louage"])
def louage_links() -> dict[str, Any]:
    """Which places each national louage station serves.

    Resolved from the 13 national stations' own destination lists against the
    station records, so each link is a real station id the client can focus.
    `unresolved` lists destinations that appear in no station record -- they are
    reported rather than dropped or guessed.
    """
    if not _LOUAGE_LINKS_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(f"{_LOUAGE_LINKS_PATH.name} is missing; run "
                    f"`python tool/build_station_index.py`"),
        )
    with _LOUAGE_LINKS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)



@app.get("/api/v1/cities", response_model=CityListResponse, tags=["Stations"])
def list_cities() -> CityListResponse:
    """Cities (governorates) with per-mode station counts.

    Computed from the same seed as `/api/v1/stations`, so the counts always
    agree with what that endpoint returns. Lets a client offer a city picker
    without downloading every stop first.
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    centres: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])

    def _bucket(city: str, mode: str | None, lat: float, lon: float) -> None:
        counts[city][mode or "unknown"] += 1
        acc = centres[city]
        acc[0] += lat
        acc[1] += lon
        acc[2] += 1

    for s in _stations:
        lat, lon = s.get("lat"), s.get("lon")
        if not lat or not lon or lat == 0 or lon == 0:
            continue
        _bucket(nearest_city(lat, lon), s.get("mode"), lat, lon)

    for s in _LOUAGE_STATIONS:
        loc = s.get("location") or {}
        lat, lon = loc.get("lat"), loc.get("lon")
        if not lat or not lon:
            continue
        # Louage hubs stay in the yellow category regardless of route mix.
        _bucket(s.get("governorate") or nearest_city(lat, lon), "louage", lat, lon)

    cities = [
        CitySummary(
            name=name,
            lat=acc[0] / acc[2],
            lon=acc[1] / acc[2],
            station_count=acc[2],
            by_mode=dict(counts[name]),
        )
        for name, acc in centres.items()
        if acc[2] > 0
    ]
    # Largest first: that is the useful order for a picker.
    cities.sort(key=lambda c: -c.station_count)
    return CityListResponse(cities=cities, count=len(cities))


@app.get("/api/v1/stations/near", response_model=NearResponse, tags=["Stations"])
def stations_near(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    limit: int = Query(10, description="Max results"),
) -> NearResponse:
    """Nearest stations to a point."""
    candidates = [s for s in _stations if s.get("lat") and s.get("lon")]
    ranked = sorted(candidates, key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))
    return NearResponse(
        near=[
            NearStation(
                id=s["id"],
                name=s["name"],
                lat=s["lat"],
                lon=s["lon"],
                dist_m=round(haversine(lat, lon, s["lat"], s["lon"])),
                lines=s.get("lines_served", []),
            )
            for s in ranked[:limit]
        ],
        query={"lat": lat, "lon": lon},
    )


# ── B3: station detail (what passes here) ─────────────────────────────────
class StationLineInfo(BaseModel):
    line_id: str
    number: str | None = None
    name: str | None = None
    mode: str
    mode_label: str
    operator: str | None = None
    color: str | None = None
    direction: str | None = None
    stops_count: int = 0
    # Where this station sits on the line, so a client can say whether the line
    # departs FROM here, terminates HERE, or merely calls here en route. Without
    # it "what passes this stop" cannot distinguish a terminus from a mid-line
    # stop, which is the difference between a useful answer and a list.
    stop_index: int | None = None
    role: str = "through"  # origin | terminus | through


class StationDetail(BaseModel):
    id: str
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    city: str | None = None
    modes: list[str]
    lines: list[StationLineInfo]
    count: int
    # False when no line's stop array references this stop. The mode is then
    # the operator's own tag rather than a routable service, and the client
    # should say so instead of rendering an empty "no lines" list as if the
    # stop were unclassified.
    lines_known: bool = False


@app.get("/api/v1/stations/{station_id}", response_model=StationDetail, tags=["Stations"])
def station_detail(station_id: str) -> StationDetail:
    """Every line that serves this stop, built from the line -> stops index.

    B3 rule: lines come from ROUTER.lines_by_station, i.e. from the lines that
    actually list this station_id in their stops. The station's own
    `lines_served` fragments are NOT used as the source, because they are
    direction-oriented and routinely have a null route_short_name and no
    stable id -- which is exactly why "what passes here" used to be unusable.
    """
    st = STATION_BY_ID.get(station_id)
    if st is None:
        raise HTTPException(status_code=404, detail=f"Station '{station_id}' not found")

    line_ids = list(dict.fromkeys(ROUTER.lines_by_station.get(station_id, [])))
    infos: list[StationLineInfo] = []
    for lid in line_ids:
        ln = LINE_BY_ID.get(lid)
        if ln is None:
            continue
        stops = ln.get("stations") or ln.get("stops") or []
        raw_mode = ln.get("mode") or "bus"
        mode = canonical_mode(raw_mode)
        # Where on the line this stop sits. A stop can appear more than once on
        # a loop service; the first occurrence is the one a rider boards at.
        idx: int | None = None
        if isinstance(stops, list):
            try:
                idx = stops.index(station_id)
            except ValueError:
                idx = None
        role = "through"
        if idx == 0:
            role = "origin"
        elif idx is not None and idx == len(stops) - 1:
            role = "terminus"
        # Direction/terminus: the end of the stop list, which is the only
        # direction information the seed actually carries.
        direction = None
        termini = ln.get("terminus") or ln.get("ends")
        if isinstance(termini, list) and len(termini) >= 2:
            direction = f"{termini[0]} - {termini[1]}"
        else:
            tail = stops[-1] if stops else None
            tail_st = STATION_BY_ID.get(tail) if isinstance(tail, str) else None
            if tail_st is not None and tail_st.get("name"):
                head_st = STATION_BY_ID.get(stops[0]) if stops else None
                head_name = (head_st or {}).get("name") or "?"
                direction = f"{head_name} - {tail_st['name']}"
        infos.append(
            StationLineInfo(
                line_id=lid,
                number=ln.get("number") or ln.get("route_id") or None,
                name=ln.get("name") or None,
                mode=mode,
                mode_label=mode_label_fr(mode),
                operator=ln.get("operator") or None,
                color=ln.get("color") or ln.get("route_color") or None,
                direction=direction,
                stops_count=len(stops),
                stop_index=idx,
                role=role,
            )
        )

    # Sort by mode in USER_MODES display order, then number, then name.
    order = {m: i for i, m in enumerate(USER_MODES)}
    infos.sort(
        key=lambda li: (
            order.get(li.mode, 99),
            (li.number or "").zfill(4),
            (li.name or ""),
        )
    )

    # `modes` is the UNION of what the stop declares and what its lines say.
    #
    # Using the lines alone was a visible contradiction: /api/v1/stations
    # colours a stop from its seed `mode` tag, so a Transtu bus stop came back
    # as `bus` in the list, while this endpoint reported `modes: []` because no
    # line's stop array lists it (only 1 562 of 7 452 stops are referenced by a
    # line). Clicking a pink bus dot opened a panel reading "Non classé", which
    # is worse than saying nothing.
    #
    # So: the declared mode is the baseline, and any mode contributed by a real
    # line is added. The client can then trust `modes` to agree with the dot.
    declared = station_modes(st)
    from_lines = [m for m in USER_MODES if any(li.mode == m for li in infos)]
    merged: list[str] = []
    for m in USER_MODES:
        if m in from_lines or m in declared:
            merged.append(m)
    if _UNCLASSIFIED in declared and not merged:
        merged.append(_UNCLASSIFIED)

    return StationDetail(
        id=st.get("id") or station_id,
        name=st.get("name"),
        lat=st.get("lat"),
        lon=st.get("lon"),
        city=st.get("city") or nearest_city(st["lat"], st["lon"]) if st.get("lat") and st.get("lon") else None,
        modes=merged,
        lines=infos,
        count=len(infos),
        # Tells the client whether the stop's mode is backed by a real line or
        # only by the operator's own tag, so the empty-lines state can be
        # phrased honestly instead of implying the stop is unclassified.
        lines_known=len(infos) > 0,
    )


def _line_detail_with_geometry(line: dict[str, Any], stops: list[StopInfo]) -> LineDetail:
    """Assemble LineDetail plus B4's geometry contract.

    Geometry honesty (C6 / A5): NEVER stitch a single straight line from the
    first stop to the last when intermediate track is missing. Each consecutive
    stop pair is reported on its own and flagged; missing ones also land in
    `gaps` with their straight-line length, so the client draws a dashed
    placeholder instead of a line crossing the country.
    """
    raw_mode = line.get("mode") or "bus"
    mode = canonical_mode(raw_mode)
    segs: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    stitched: list[list[float]] = []
    complete = True

    for a, b in zip(stops, stops[1:]):
        if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
            continue
        pts = _geometry_for(a.stop_id, b.stop_id)
        gap_m = _haversine_km(a.lat, a.lon, b.lat, b.lon) * 1000.0
        segs.append(
            {
                "from_stop_id": a.stop_id,
                "to_stop_id": b.stop_id,
                "from_name": a.name,
                "to_name": b.name,
                "has_geometry": bool(pts),
                "needs_geometry": (not pts) and gap_m >= 300.0,
                "gap_m": round(gap_m),
                "geometry": pts,
            }
        )
        if pts:
            # Cache polylines are [[lat, lon]]; stitch in that order.
            stitched.extend(pts if not stitched else pts[1:])
        elif gap_m >= 300.0:
            complete = False
            gaps.append(
                {
                    "from_stop_id": a.stop_id,
                    "to_stop_id": b.stop_id,
                    "from_name": a.name,
                    "to_name": b.name,
                    "gap_m": round(gap_m),
                    "reason": "no_cached_geometry",
                }
            )

    geometry: dict[str, Any] | None = None
    if complete and len(stitched) >= 2:
        # GeoJSON wants [[lon, lat]].
        geometry = {"type": "LineString", "coordinates": [[p[1], p[0]] for p in stitched]}

    return LineDetail(
        line=line,
        stops=stops,
        count=len(stops),
        mode=mode,
        mode_label=mode_label_fr(mode),
        geometry=geometry,
        geometry_complete=complete,
        geometry_segments=segs,
        gaps=gaps,
    )


@app.get("/api/v1/lines", response_model=LinesResponse, tags=["Lines"])
def get_lines() -> LinesResponse:
    """All transport lines (keyed by unique id; number is filterable)."""
    return LinesResponse(
        lines=[
            LineSummary(
                id=l.get("id", ""),
                number=l.get("number"),
                short_name=l.get("short_name"),
                long_name=l.get("long_name"),
                mode=l.get("mode", "bus"),
                color=l.get("color"),
                route_id=l.get("route_id"),
                stops_count=len(l.get("stations") or l.get("stops") or []),
            )
            for l in _lines
        ],
        count=len(_lines),
    )


@app.get("/api/v1/lines/{line_identifier}", response_model=LineDetail, tags=["Lines"])
def get_line(line_identifier: str) -> LineDetail:
    """Return a line by unique id OR by number (number is not unique)."""
    # Try id first
    line = LINE_BY_ID.get(line_identifier)
    if line is None:
        # Try by number
        by_num = LINES_BY_NUMBER.get(line_identifier)
        if by_num:
            line = by_num[0]
            log.info(
                "Line lookup by number '%s' returned %d matches; using first: %s",
                line_identifier, len(by_num), line.get("id"),
            )
        else:
            raise HTTPException(status_code=404, detail=f"Line '{line_identifier}' not found")
    stations_list = line.get("stations") or line.get("stops") or []
    stops: list[StopInfo] = []
    if stations_list and isinstance(stations_list[0], (int, str)):
        for sid in stations_list:
            st = STATION_BY_ID.get(sid)
            if st is None:
                log.warning("Stop id %s in line %s not found in station index", sid, line.get("id"))
                continue
            stops.append(
                StopInfo(
                    stop_id=st.get("id"),
                    name=st.get("name"),
                    lat=st.get("lat"),
                    lon=st.get("lon"),
                    lines=st.get("lines_served"),
                )
            )
    elif stations_list and isinstance(stations_list[0], dict):
        for s in stations_list:
            stops.append(
                StopInfo(
                    name=s.get("name", s.get("station", "")),
                    lat=s.get("lat", s.get("latitude")),
                    lon=s.get("lon", s.get("longitude")),
                    order=s.get("order"),
                    schedule=s.get("schedule"),
                )
            )
    else:
        for s in line.get("stops", []):
            stops.append(
                StopInfo(
                    name=s.get("name"),
                    lat=s.get("lat"),
                    lon=s.get("lon"),
                    order=s.get("order"),
                    schedule=s.get("schedule"),
                    stop_id=s.get("stop_id"),
                )
            )
    return _line_detail_with_geometry(line, stops)


@app.get("/api/v1/route/plan", tags=["Routing"])
def route_plan_endpoint(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
    modes_include: str | None = Query(
        None, description="Comma-separated modes to allow, e.g. bus,metro,walk"
    ),
    modes_exclude: str | None = Query(
        None, description="Comma-separated modes to forbid, e.g. train,metro"
    ),
    objective: str = Query("fastest", description="fastest | cheapest | fewest_transfers"),
    max_transfers: int | None = Query(None, ge=0, description="Cap on line changes"),
    max_walk_m: float | None = Query(None, gt=0, description="Cap access+egress walk (m)"),
    max_itineraries: int = Query(3, ge=1, le=8),
) -> dict[str, Any]:
    """Multi-objective, mode-filtered routing (B2 / B5).

    This is THE routing endpoint. /api/v1/route/transit and
    /api/v1/route/options are kept working for existing clients and are now
    thin wrappers over the same planner, so there is one ranking implementation
    rather than three half-working ones (C3, B2).

    Filters are HARD: modes_exclude is applied inside Dijkstra edge expansion,
    so an excluded mode cannot appear in any leg (D1).

    Example:
      curl "http://127.0.0.1:8000/api/v1/route/plan?start_lat=36.8065&start_lon=10.1815\
&end_lat=36.7598&end_lon=10.1906&modes_exclude=metro&objective=fewest_transfers"
    """
    def _split(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]

    try:
        return ROUTER.route_plan(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
            include=_split(modes_include),
            exclude=_split(modes_exclude),
            objective=objective,
            max_transfers=max_transfers,
            max_walk_m=max_walk_m,
            max_itineraries=max_itineraries,
        )
    except ValueError as exc:
        # Unknown mode, impossible filter, bad objective -> 400 with the
        # available modes, never a silent empty result (B1).
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/route", tags=["Routing"])
def route(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Driving route from OSRM (car profile)."""
    result = query_osrm((start_lat, start_lon), (end_lat, end_lon))
    if not result or result.get("code") != "Ok" or not result.get("routes"):
        if result is None:
            return JSONResponse(
                {
                    "error": "OSRM is unreachable",
                    "detail": f"Cannot reach {OSRM_URL}. Set OSRM_URL or start osrm-routed.",
                    "source": "osrm",
                },
                status_code=503,
            )
        return {"error": "No route found", "source": "osrm"}
    route_data = result["routes"][0]
    return {
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon},
        "distance_m": round(route_data["distance"]),
        "duration_s": round(route_data["duration"]),
        "waypoints": result.get("waypoints", []),
        "geometry": route_data.get("geometry"),
        "source": "osrm",
    }


# ── Local transit router endpoint ─────────────────────────────────────────
#
# Physical-cost multi-modal Dijkstra over the seed (stations + lines).
# Outputs the same 3-alternative envelope the frontend computeTransit()
# renderer expects (best_fastest / best_less_walk / alternatives) so the
# existing safe-DOM map plotter can draw it without another code path.
#
# Steps are translated from the router's internal {type, from, to, ...} dicts
# into the frontend's {type, start:[lat,lon], end:[lat,lon], color, stop_name,
# mode, line} shape.  Mode colour comes from the inline `colors` map already in
# index.html (bus / metro / train / rfr / default).
#
def _mode_color(mode: str) -> str:
    return {
        "metro": "#339af0",
        "train": "#845ef7",
        "rfr": "#ff922b",
        "bus": "#e03131",
    }.get(mode, "#8b949e")


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(
        math.radians(lon2 - lon1) / 2
    ) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _leg_from_step(step: dict[str, Any], gap_breaks: bool = False) -> dict[str, Any]:
    """One leg from one step.

    A leg with no real path is marked `needs_geometry`; the map must draw
    nothing, or an explicit unverified placeholder, rather than a straight line
    across open country. `geometry_gap_m` says how far that omission spans.
    `gap_breaks` records that this leg is a hole in an otherwise continuous ride.
    """
    geom = step.get("geometry") or []
    frm, to = step.get("start"), step.get("end")
    gap_m = None
    if len(geom) < 2 and frm and to:
        gap_m = round(_haversine(frm[0], frm[1], to[0], to[1]))
    return {
        "mode": step.get("mode"),
        "type": step.get("type"),
        "line": step.get("line"),
        "from": frm,
        "to": to,
        "from_name": step.get("from_name"),
        "to_name": step.get("to_name"),
        "from_id": step.get("from_id"),
        "to_id": step.get("to_id"),
        "geometry": geom,
        "has_geometry": len(geom) >= 2,
        "geometry_missing": len(geom) < 2,
        # The client draws nothing (or a dashed "unverified" placeholder) when
        # this is true, rather than a straight line.
        "needs_geometry": bool(step.get("needs_geometry")) and len(geom) < 2,
        "geometry_gap_m": gap_m,
        "breaks_continuity": gap_breaks,
        "distance_m": step.get("distance_m"),
        "straight_m": step.get("straight_m"),
        "time_seconds": step.get("time_seconds"),
        "duration": step.get("time_seconds"),
    }


def _steps_to_legs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten steps into one entry per movement, in travel order.

    A leg is a movement the rider actually performs: walk, a ride on one line, a
    transfer, or a taxi hop. Consecutive ride steps on the SAME line are merged
    into one leg so the list reads as "board, ride, alight" rather than one entry
    per intermediate stop.

    A sub-step with no polyline BREAKS the merge instead of being stitched over.
    Concatenating across it produces one discontinuous line that jumps over open
    country: measured 93 km of polyline for a 214 km journey, because the
    125 km Borj Cedria -> Sidi Bou Goubrine gap in the seed has no rail geometry
    and none can be invented for it. The gap becomes its own leg, flagged, so the
    two real stretches stay real and the hole is reported rather than drawn.
    """
    legs: list[dict[str, Any]] = []
    for s in steps:
        kind = s.get("type")
        mode = s.get("mode") or ("walk" if kind == "walk" else kind)
        line = s.get("line")
        geom = s.get("geometry") or []
        prev = legs[-1] if legs else None
        mergeable = (
            kind == "ride"
            and prev is not None
            and prev.get("type") == "ride"
            and prev.get("mode") == mode
            and (prev.get("line") or None) == (line or None)
        )
        # A real hole in the ride breaks the merge in BOTH directions. The gap
        # can be the step being appended OR the leg already accumulated: the
        # first step of a ride may itself be the unmatchable one, and appending
        # the next step onto it would silently swallow the hole and stitch two
        # real stretches into one discontinuous line.
        prev_has_hole = bool(
            mergeable and prev.get("needs_geometry")
        )
        if mergeable and (prev_has_hole or (not geom and s.get("needs_geometry"))):
            legs.append(_leg_from_step(s, gap_breaks=prev_has_hole))
            continue
        if mergeable:
            if geom:
                prev["geometry"] = (prev.get("geometry") or []) + geom
            if s.get("to_id"):
                prev["to_id"] = s.get("to_id")
            prev["to"] = s.get("end")
            prev["to_name"] = s.get("to_name")
            # The merged leg is a new object: its endpoints and polyline differ
            # from the first step it absorbed, so the geometry flags must be
            # re-derived rather than inherited.
            prev["has_geometry"] = len(prev.get("geometry") or []) >= 2
            prev["geometry_missing"] = not prev["has_geometry"]
            prev["needs_geometry"] = False
            prev["geometry_gap_m"] = (
                None
                if prev["has_geometry"] or not (prev.get("from") and prev.get("to"))
                else round(_haversine(
                    prev["from"][0], prev["from"][1],
                    prev["to"][0], prev["to"][1],
                ))
            )
            prev["distance_m"] = round(
                (prev.get("distance_m") or 0) + (s.get("distance_m") or 0)
            )
            prev["time_seconds"] = round(
                (prev.get("time_seconds") or 0) + (s.get("time_seconds") or 0), 1
            )
            continue
        legs.append(_leg_from_step(s))
    return legs
def _router_to_option(router_out: dict[str, Any]) -> dict[str, Any]:
    """Convert a Router.route() dict into the frontend 3-alternative envelope."""
    mode = router_out.get("mode")
    if mode == "walk":
        # walk-only: no transit alternatives; just return the walk as best_fastest.
        steps_raw = router_out.get("steps", [])
        return {
            "duration": round(router_out.get("duration_min", 0) * 60, 1),
            "duration_min": router_out.get("duration_min", 0),
            "transfers": 0,
            "has_walk_transfer": True,
            "steps": [
                {
                    "type": "walk",
                    "start": [s["from"]["lat"], s["from"]["lon"]],
                    "end": [s["to"]["lat"], s["to"]["lon"]],
                    "color": "#8E8E93",
                    "stop_name": s.get("label", ""),
                    "to_name": s.get("to_name"),
                    "from_name": s.get("from_name"),
                    "geometry": [],
                    "has_geometry": False,
                    "mode": "walk",
                    "line": None,
                }
                for s in steps_raw
            ],
        }

    dur_min = router_out.get("duration_min", 0)
    steps_out: list[dict[str, Any]] = []
    transfer_count = 0
    steps_raw = router_out.get("steps", [])
    prev_mode: str | None = None
    after_transfer = False
    for s in steps_raw:
        t = s.get("type", "ride")
        line = s.get("line") or ""
        st_mode = s.get("mode", "bus") if t == "ride" else t
        fr, to = s.get("from", {}), s.get("to", {})
        fr_lat = fr.get("lat") if isinstance(fr, dict) else fr[0] if isinstance(fr, list) else 0.0
        fr_lon = fr.get("lon") if isinstance(fr, dict) else fr[1] if isinstance(fr, list) else 0.0
        to_lat = to.get("lat") if isinstance(to, dict) else to[0] if isinstance(to, list) else 0.0
        to_lon = to.get("lon") if isinstance(to, dict) else to[1] if isinstance(to, list) else 0.0
        # transfer detection: a transfer step already counts; also count mode
        # changes between consecutive ride segments (legacy path, in case a
        # transfer step was not emitted). These are mutually exclusive across
        # iterations — a bus->train transfer produces BOTH a "transfer" step
        # AND a mode change on the next ride, so we suppress the mode-change
        # check on the ride immediately following a transfer.
        if t == "transfer":
            transfer_count += 1
            after_transfer = True
        elif t == "ride" and prev_mode is not None and prev_mode != st_mode:
            if not after_transfer:
                transfer_count += 1
            after_transfer = False
        if t != "transfer":
            after_transfer = False
        # has_walk_transfer: any walk segment that is not the start/end access
        # walk (i.e. an intermediate walk between lines) counts as a walk-transfer.
        has_walk_transfer = any(
            ss.get("type") == "walk"
            for ss in steps_raw[1:-1]  # exclude first (access) and last (egress)
        )
        # Real geometry for this leg, when the cache has it. Walk legs are
        # deliberately left straight: footways are absent from the OSRM driving
        # profile used to build the cache, and walk legs are <= 900 m where the
        # straight line is visually indistinguishable.
        # Real geometry now travels with the step itself: the graph edge the
        # search traversed carries the polyline it priced. _geometry_for remains
        # as a fallback for a step that somehow arrives without one.
        geom: list[list[float]] = s.get("geometry") or []
        if not geom and t == "ride" and not s.get("needs_geometry"):
            # Only fall back to the station-pair cache when the router did not
            # flag the leg. A flagged leg means no real path exists, and
            # re-deriving a straight line here is the false line being reported.
            geom = _geometry_for(s.get("from_id"), s.get("to_id"))
        steps_out.append({
            "type": t,
            "start": [fr_lat, fr_lon],
            "end": [to_lat, to_lon],
            "color": _mode_color(st_mode if t == "ride" else "walk"),
            "stop_name": (s.get("to_name") or s.get("label") or "").strip(),
            # to_name / from_name are the station names. They are sent
            # separately because stop_name falls back to the human-readable
            # label, which for a walk or taxi leg is instructional text
            # ("Marcher 869 m jusqu'a destination"). Without these the client
            # cannot tell a place name from an instruction and labels the
            # numbered milestones with the instruction instead.
            "to_name": s.get("to_name"),
            "from_name": s.get("from_name"),
            "mode": st_mode,
            "line": line if t == "ride" else None,
            "geometry": geom,
            "has_geometry": len(geom) >= 2,
            # Real per-leg metrics, straight from the graph edge.
            "distance_m": s.get("distance_m"),
            "time_seconds": s.get("time_seconds"),
            # Station ids. The map needs these to show only the stations this
            # itinerary touches, and the geometry lookup falls back to them.
            "from_id": s.get("from_id"),
            "to_id": s.get("to_id"),
            "straight_m": s.get("straight_m"),
            # Long enough that a missing polyline is visible on the map: the
            # client must not fall back to a straight line.
            "needs_geometry": s.get("needs_geometry", False),
        })
        prev_mode = st_mode if t == "ride" else prev_mode

    return {
        "duration": round(dur_min * 60, 1),
        "duration_min": dur_min,
        "transfers": transfer_count,
        "has_walk_transfer": has_walk_transfer,
        "steps": steps_out,
        "fare_dinars": router_out.get("fare_dinars"),
    }


@app.get("/api/v1/route/transit", tags=["Routing"])
def route_transit(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Local multi-modal transit itinerary (physical-cost Dijkstra).

    Reuses the router's already-loaded seed via STATION_BY_ID / _lines.  The
    response uses the same 3-alternative envelope as the (now-removed)
    tunismapper proxy so the frontend renderer needs no new code path.
    """
    result = ROUTER.route(start_lat, start_lon, end_lat, end_lon)
    if result.get("error"):
        return {"error": result["error"], "source": "local-router"}

    option = _router_to_option(result)
    if not option.get("steps"):
        return {"error": "No transit route found", "source": "local-router"}

    return {
        "best_fastest": option,
        "best_less_walk": None,
        "alternatives": [],
        # Explicit multi-modal leg list: one entry per movement, each with its
        # own real geometry. `steps` above is kept byte-identical for the
        # existing frontend renderer, so nothing that already consumes this
        # endpoint changes shape.
        "legs": _steps_to_legs(option.get("steps", [])),
        "source": "local-router",
    }


# ── Three distinct transport options ───────────────────────────────────────
# The user picks a transport option; each is searched SEPARATELY with its own
# mode restriction rather than being sliced out of one combined answer. A
# combined search minimises total time and will return a train when the user
# asked for a bus, so deriving per-option results from it produces confidently
# wrong options. Each option reports whether it is available, so the frontend
# can grey out "Train" on a trip with no rail rather than showing an empty card.
OPTION_LABELS: dict[str, str] = {
    "bus": "Bus",
    "louaj": "Taxi / Louage",
    "train": "Train / Metro",
}


def _station_ids_used(steps: list[dict[str, Any]]) -> list[str]:
    """Station ids the itinerary actually touches, in travel order.

    Only the stations the rider boards, alights or transfers at. The map uses
    this to hide every other marker once a route is drawn.
    """
    used: list[str] = []
    for s in steps:
        for key in ("from_id", "to_id"):
            sid = s.get(key)
            if sid and sid not in used:
                used.append(sid)
    return used


@app.get("/api/v1/route/options", tags=["Routing"])
def route_options(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Three separately-computed transport options for one origin/destination.

    Returns one entry per option (bus, louaj/taxi, train/metro). Each is its own
    mode-restricted search, so "Bus" contains only bus-family legs and "Train"
    only rail-family legs. An option that cannot be served is returned with
    `available: false` and a reason rather than being omitted, so the UI can
    show it as unavailable instead of silently hiding it.

    The envelope keeps `best_fastest` / `legs` / `stations_used` so a caller
    already using /route/transit can migrate without a flag day.
    """
    options: list[dict[str, Any]] = []
    for key in ("bus", "louaj", "train"):
        modes = OPTION_MODES.get(key)
        res = ROUTER.route(start_lat, start_lon, end_lat, end_lon, allowed_modes=modes)
        entry: dict[str, Any] = {
            "id": key,
            "label": OPTION_LABELS[key],
            "modes": sorted(m for m in modes if m != "walk"),
        }
        if res.get("error") or not res.get("steps"):
            entry.update({
                "available": False,
                "reason": res.get("error") or "no route with these modes",
                "duration_min": None,
                "legs": [],
                "stations_used": [],
            })
            options.append(entry)
            continue
        opt = _router_to_option(res)
        steps = opt.get("steps", [])
        legs = _steps_to_legs(steps)
        # A taxi/louaj answer is a single direct leg by construction; anything
        # longer means the restricted search fell through to something else and
        # the label would be a lie.
        if key == "louaj" and not any(l["mode"] in ("taxi", "louaj") for l in legs):
            entry.update({
                "available": False,
                "reason": "no louaj/taxi option for this trip",
                "duration_min": None,
                "legs": [],
                "stations_used": [],
            })
            options.append(entry)
            continue
        entry.update({
            "available": True,
            "reason": None,
            "duration_min": opt.get("duration_min"),
            "duration_seconds": opt.get("duration"),
            "transfers": opt.get("transfers"),
            "has_walk_transfer": opt.get("has_walk_transfer"),
            "fare_dinars": opt.get("fare_dinars"),
            "legs": legs,
            "steps": steps,
            "stations_used": _station_ids_used(steps),
            "geometry_complete": all(l.get("has_geometry") for l in legs
                                    if l["mode"] not in ("walk", "transfer")),
        })
        options.append(entry)

    available = [o for o in options if o.get("available")]
    fastest = min(available, key=lambda o: o["duration_min"]) if available else None
    return {
        "options": options,
        "best_id": fastest["id"] if fastest else None,
        "stations_used": fastest["stations_used"] if fastest else [],
        "source": "local-router",
    }


def _families_in_steps(steps: list[dict[str, Any]]) -> frozenset[str]:
    """Which transport families an itinerary actually uses."""
    out: set[str] = set()
    for s in steps:
        mode = s.get("mode")
        if s.get("type") == "taxi" or mode in ("taxi", "louaj"):
            out.add("louaj")
        elif mode in ("bus", "rfr", "tram"):
            out.add("bus")
        elif mode in ("train", "rail", "metro"):
            out.add("train")
    return frozenset(out)


def _itinerary_signature(steps: list[dict[str, Any]]) -> tuple:
    """Identity of a path: the ordered movements that actually move the rider.

    Walks and transfers do not change which service is used, so two paths that
    differ only in where a walk happened are the same itinerary and must not
    both be offered.
    """
    return tuple(
        (s.get("type"), s.get("mode"), s.get("line") or "", s.get("from_id") or "",
         s.get("to_id") or "")
        for s in steps
        if s.get("type") in ("ride", "taxi")
    )


@app.get("/api/v1/route/modes", tags=["Routing"])
def route_modes(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
    modes: str = Query(
        ...,
        description=(
            "Comma-separated transport families the user selected. Any "
            "non-empty subset of: bus, louaj, train. e.g. 'bus', 'bus,train', "
            "'bus,louaj,train'."
        ),
    ),
    max_itineraries: int = Query(
        3, ge=1, le=6, description="How many distinct itineraries to return"
    ),
) -> dict[str, Any]:
    """Every distinct itinerary that respects the user's mode selection.

    The selection is a set of transport FAMILIES and any non-empty subset is
    legal: 'bus', 'train', 'louaj', 'bus,train', 'bus,louaj', 'train,louaj',
    'bus,louaj,train'. Each itinerary is its own mode-restricted search over the
    families actually used, so a "Bus + Train" answer that never touches a train
    is filtered out rather than padded.

    Geometry honesty: `geometry_complete` is true only when EVERY non-walk leg
    carries a real polyline, and `straight_leg_count` says how many do not. A
    leg with no real path is flagged `needs_geometry` and the client must not
    draw it straight -- the seed's SNCFT lines list stops hundreds of km apart,
    so those holes are permanent and are reported instead of invented.
    """
    selected = [m.strip().lower() for m in modes.split(",") if m.strip()]
    try:
        allowed = modes_for(selected)
    except ValueError as exc:
        return {"error": str(exc), "available_families": list(FAMILIES)}
    if allowed is None:
        return {
            "error": "at least one transport family must be selected",
            "available_families": list(FAMILIES),
        }

    sel = frozenset(selected)

    # The unrestricted-within-selection search is what finds genuinely
    # multi-modal paths (bus then train); the per-family searches then supply the
    # single-mode alternatives. Restricting to one family at a time cannot.
    results: list[dict[str, Any]] = []
    res = ROUTER.route(start_lat, start_lon, end_lat, end_lon,
                       allowed_modes=allowed)
    if not res.get("error") and res.get("steps"):
        results.append(res)
    for fam in sorted(sel):
        sub = ROUTER.route(start_lat, start_lon, end_lat, end_lon,
                           allowed_modes=modes_for([fam]))
        if not sub.get("error") and sub.get("steps"):
            results.append(sub)

    seen: set[tuple] = set()
    itineraries: list[dict[str, Any]] = []
    for r in results:
        opt = _router_to_option(r)
        steps = opt.get("steps", [])
        if not steps:
            continue
        fams_used = _families_in_steps(steps)
        # An itinerary that ignores part of the selection is not what was asked
        # for: offering a "Train" journey for a bus-only request is the failure
        # this guards against.
        if not fams_used or not fams_used <= sel:
            continue
        sig = _itinerary_signature(steps)
        if sig in seen:
            continue
        seen.add(sig)
        legs = _steps_to_legs(steps)
        rides = [l for l in legs if l["mode"] not in ("walk", "transfer")]
        itineraries.append({
            "label": label_for(fams_used),
            "families": sorted(fams_used),
            "duration_min": opt.get("duration_min"),
            "duration_seconds": opt.get("duration"),
            "transfers": opt.get("transfers"),
            "fare_dinars": opt.get("fare_dinars"),
            "legs": legs,
            "steps": steps,
            "stations_used": _station_ids_used(steps),
            "geometry_complete": all(l.get("has_geometry") for l in rides),
            "straight_leg_count": sum(1 for l in rides if not l.get("has_geometry")),
            "gaps": [
                {
                    "from_name": l.get("from_name"),
                    "to_name": l.get("to_name"),
                    "gap_m": l.get("geometry_gap_m"),
                }
                for l in legs if l.get("needs_geometry")
            ],
        })

    itineraries.sort(key=lambda i: i["duration_min"] or float("inf"))
    return {
        "selected_modes": sorted(sel),
        "selected_label": label_for(sel),
        "itineraries": itineraries[:max_itineraries],
        "total_found": len(itineraries),
        "available_families": list(FAMILIES),
        "combinations_available": [
            sorted(k) for k in sorted(COMBINATIONS, key=lambda s: (len(s), sorted(s)))
        ],
        "source": "local-router",
    }


@app.get("/api/v1/itinerary", tags=["Routing"])
def itinerary(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Transit itinerary endpoint.

    Formerly proxied to tunismapper.com. Disabled by default pending provenance
    review (docs/provenance.md). Set ENABLE_TUNISMAPPER_PROXY=true to re-enable.
    """
    if not ENABLE_TUNISMAPPER_PROXY:
        return JSONResponse(
            {
                "error": "Transit itinerary service is disabled by default.",
                "detail": (
                    "The previous tunismapper.com proxy is off pending a provenance "
                    "review (docs/provenance.md). Set ENABLE_TUNISMAPPER_PROXY=true to "
                    "re-enable, or use the local transit router when it is available."
                ),
                "source": "disabled",
            },
            status_code=410,
        )
    url = (
        "https://www.tunismapper.com/backend/api/itinerary.php"
        f"?startLat={start_lat}&startLng={start_lon}"
        f"&endLat={end_lat}&endLng={end_lon}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _OSM_UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e), "source": "tunismapper"}


@app.get("/api/v1/search", tags=["Stations"])
def search_places(
    q: str = Query(..., min_length=2, description="Free-text place or stop name"),
    limit: int = Query(8, ge=1, le=25, description="Max results"),
    near_lat: float | None = Query(None, description="Bias results toward this latitude"),
    near_lon: float | None = Query(None, description="Bias results toward this longitude"),
) -> dict[str, Any]:
    """Search the network's own stops and cities by name.

    This exists so a rider can pick an origin or destination by NAME, without
    ever typing a latitude or longitude. The stops themselves are searched
    first, because a stop hit is strictly better than a geocoder hit here: it
    is a place a vehicle actually stops, and it comes back already tied to the
    station id, so the client can show its lines immediately.

    Ranking is exact match, then prefix, then substring, with a distance
    tiebreak when the client supplies a reference point — so two stops both
    named "20 Mars" resolve to the one actually near the rider.

    `kind` is `stop` or `city` so the client can label and icon each hit.
    """
    needle = q.strip().lower()
    if len(needle) < 2:
        return {"results": [], "query": q, "count": 0}

    def _score(name: str) -> int:
        n = name.strip().lower()
        if n == needle:
            return 0
        if n.startswith(needle):
            return 1
        return 2

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for s in _stations:
        lat, lon = s.get("lat"), s.get("lon")
        if not lat or not lon:
            continue
        name = s.get("name") or ""
        if needle not in name.lower():
            continue
        sid = s.get("id") or ""
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        city = nearest_city(lat, lon)
        results.append(
            {
                "kind": "stop",
                "id": sid,
                "name": name.strip(),
                "lat": lat,
                "lon": lon,
                "modes": station_modes(s),
                "city": city,
                "score": _score(name),
                "display_name": f"{name.strip()} · {city}",
            }
        )

    # Louage hubs are not in _stations but are real, pickable places.
    for s in _LOUAGE_STATIONS:
        loc = s.get("location") or {}
        lat, lon = loc.get("lat"), loc.get("lon")
        if not lat or not lon:
            continue
        name = s.get("name_fr") or s.get("name_en") or s.get("id") or ""
        if needle not in name.lower():
            continue
        sid = f"louage_{s.get('id')}"
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        results.append(
            {
                "kind": "stop",
                "id": sid,
                "name": name.strip(),
                "lat": lat,
                "lon": lon,
                "modes": ["louaj"],
                "city": s.get("governorate") or nearest_city(lat, lon),
                "score": _score(name),
                "display_name": f"{name.strip()} · Taxi / Louage",
            }
        )

    for name, slat, slon in CITY_SEATS:
        if needle not in name.lower():
            continue
        results.append(
            {
                "kind": "city",
                "id": f"city_{name}",
                "name": name,
                "lat": slat,
                "lon": slon,
                "modes": [],
                "city": name,
                "score": _score(name),
                "display_name": name,
            }
        )

    def _dist(r: dict[str, Any]) -> float:
        if near_lat is None or near_lon is None:
            return 0.0
        return _haversine_km(near_lat, near_lon, r["lat"], r["lon"])

    results.sort(key=lambda r: (r["score"], _dist(r), r["name"]))

    return {
        "results": [{k: v for k, v in r.items() if k != "score"} for r in results[:limit]],
        "query": q,
        "count": len(results),
    }


@app.get("/api/v1/geocode", tags=["Stations"])
def geocode(
    q: str = Query(..., description="Place name to search in Tunisia"),
    limit: int = Query(3, description="Max results"),
) -> dict[str, Any]:
    """Geocode a place name via Nominatim (served through the backend to avoid
    browser User-Agent headers and to cache results)."""
    data = query_nominatim(q)
    if not data:
        return JSONResponse(
            {"error": "Geocoding service unreachable", "source": "nominatim"},
            status_code=503,
        )

    results = [
        {
            "lon": float(d["lon"]),
            "lat": float(d["lat"]),
            "display_name": d.get("display_name", ""),
            "type": d.get("type", ""),
        }
        for d in data[:limit]
    ]
    return {"query": q, "results": results, "count": len(results)}


@app.get("/favicon.svg", tags=["System"], response_model=None)
def favicon_svg() -> FileResponse | JSONResponse:
    """Serve the app icon.

    Lives in frontend/static/ (SvelteKit's static-asset root, copied verbatim
    into frontend/build/) rather than the frontend root, which is not served.
    Check both so a dev-server-only layout still resolves.
    """
    for rel in ("frontend/build/favicon.svg", "frontend/static/favicon.svg"):
        icon = BASE / rel
        if icon.exists():
            return FileResponse(icon, media_type="image/svg+xml")
    return JSONResponse({"error": "no favicon"}, status_code=404)


@app.get("/", tags=["System"], response_model=None)
def index() -> FileResponse | JSONResponse:
    """Serve the built frontend, if it has been built.

    This used to return `FileResponse(BASE / "frontend" / "index.html")`, which
    was the Flutter-web output directory. That file does not exist any more, so
    the route raised `RuntimeError: File at path ... does not exist` and every
    request to `/` produced a 500 traceback. SvelteKit builds to
    `frontend/build/`, so that is what we serve now.

    When nothing has been built, return 503 with the command to fix it, rather
    than a 500 with a stack trace -- an unbuilt frontend is a setup state, not a
    server fault, and the person hitting it is usually the developer who can act
    on the hint.
    """
    built = BASE / "frontend" / "build" / "index.html"
    if built.exists():
        return FileResponse(built)
    return JSONResponse(
        {
            "error": "frontend has not been built",
            "hint": (
                "cd frontend && npm run build   "
                "(or run the dev server: cd frontend && npm run dev, then use :5173)"
            ),
        },
        status_code=503,
    )


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=8000)
