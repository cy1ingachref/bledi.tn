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
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# Local transit router (physical-cost Dijkstra).
from src.backend.app.routing import Router

log = logging.getLogger("bledi")

# ── Paths ──────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parents[3]  # repo root
SEED_PATH = BASE / "data" / "seed_all_tunisia_routes.json"
SEED_TAGED_PATH = BASE / "data" / "seed_all_tunisia_routes.tagged.json"

# Prefer the tagged file if it exists, else fall back to the original.
_SEED_PATH = SEED_TAGED_PATH if SEED_TAGED_PATH.exists() else SEED_PATH

# ── Config ──────────────────────────────────────────────────────────────
OSRM_URL = os.environ.get(
    "OSRM_URL",
    "https://router.project-osrm.org/route/v1/driving",
)
OSRM_TIMEOUT = int(os.environ.get("OSRM_TIMEOUT", "30"))
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173",
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
    ("Ghorbel", 35.2292, 9.1789),
    ("Tozeur", 33.9197, 6.9440),
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
        features.append(
            StationGeoJSON(
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties={
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "name_en": s.get("name_en"),
                    "mode": s.get("mode"),
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
        modes = {r.get("mode") for r in routes if r.get("mode")}
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
                    # A stop can serve several louage types; report them all and
                    # let the client treat any of them as the yellow category.
                    "mode": next(iter(modes)) if len(modes) == 1 else "louage",
                    "modes": sorted(modes) or ["louage"],
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

    return StationsResponse(
        features=features,
        metadata=StationsMeta(count=len(features), total=len(_stations)),
    )


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
    return LineDetail(line=line, stops=stops, count=len(stops))


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
        steps_out.append({
            "type": t,
            "start": [fr_lat, fr_lon],
            "end": [to_lat, to_lon],
            "color": _mode_color(st_mode if t == "ride" else "walk"),
            "stop_name": (s.get("to_name") or s.get("label") or "").strip(),
            "mode": st_mode,
            "line": line if t == "ride" else None,
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
    icon = BASE / "frontend" / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    return JSONResponse({"error": "no favicon"}, status_code=404)


@app.get("/", tags=["System"], response_model=None)
def index() -> FileResponse:
    return FileResponse(BASE / "frontend" / "index.html")


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=8000)
