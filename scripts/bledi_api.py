#!/usr/bin/env python3
"""FastAPI backend for bledi.tn — routing + station data."""

import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

BASE = Path(__file__).resolve().parent.parent
SEED = BASE / "data/seed_all_tunisia_routes.json"
OSRM_URL = os.environ.get("OSRM_URL", "http://localhost:5000/route/v1/driving")

app = FastAPI(title="bledi.tn", description="Tunisia public transport routing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache seed at startup — avoids re-reading 1.7 MB JSON on every request
with SEED.open(encoding="utf-8") as _f:
    SEED_DATA: dict[str, Any] = json.load(_f)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def query_osrm(start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any] | None:
    # overview=full returns the full road geometry so the frontend can draw the actual route
    url = f"{OSRM_URL}/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full&geometries=geojson"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bledi.tn/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


@app.get("/api/stations")
def get_stations():
    """Return all stations as GeoJSON FeatureCollection."""
    features = []
    for s in SEED_DATA["stations"]:
        if s.get("lat") == 0 or s.get("lon") == 0:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            "properties": {
                "id": s["id"],
                "name": s["name"],
                "lines": s.get("lines_served", []),
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count": len(features),
            "total": len(SEED_DATA["stations"]),
        },
    }


@app.get("/api/stations/near")
def stations_near(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    limit: int = Query(10, description="Max results"),
) -> dict[str, Any]:
    """Return nearest stations to a point."""
    candidates = [s for s in SEED_DATA["stations"] if s.get("lat") and s.get("lon")]
    ranked = sorted(candidates, key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))
    return {
        "near": [
            {
                "id": s["id"],
                "name": s["name"],
                "lat": s["lat"],
                "lon": s["lon"],
                "dist_m": round(haversine(lat, lon, s["lat"], s["lon"])),
                "lines": s.get("lines_served", []),
            }
            for s in ranked[:limit]
        ],
        "query": {"lat": lat, "lon": lon},
    }


@app.get("/api/route")
def route(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Return driving route from OSRM."""
    result = query_osrm((start_lat, start_lon), (end_lat, end_lon))
    if not result or result.get("code") != "Ok" or not result.get("routes"):
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


@app.get("/api/itinerary")
def itinerary(
    start_lat: float = Query(..., description="Start latitude"),
    start_lon: float = Query(..., description="Start longitude"),
    end_lat: float = Query(..., description="End latitude"),
    end_lon: float = Query(..., description="End longitude"),
) -> dict[str, Any]:
    """Transit itinerary endpoint.

    Formerly proxied to tunismapper.com. That behavior is now disabled by
    default because the data source's terms have not been verified (see
    docs/provenance.md). Set ENABLE_TUNISMAPPER_PROXY=true to re-enable.

    When disabled, returns 410 so the frontend can fall back to the local router.
    """
    if os.environ.get("ENABLE_TUNISMAPPER_PROXY", "").strip().lower() not in (
        "1", "true", "yes",
    ):
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
        req = urllib.request.Request(url, headers={"User-Agent": "bledi.tn/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e), "source": "tunismapper"}


@app.get("/api/lines")
def get_lines():
    """Return all transport lines."""
    return {
        "lines": [
            {
                "number": l.get("number"),
                "short_name": l.get("short_name"),
                "long_name": l.get("long_name"),
                "type": l.get("type", "bus"),
                "color": l.get("color"),
                "route_id": l.get("route_id"),
                "stops_count": len(l.get("stops", [])),
            }
            for l in SEED_DATA["lines"]
        ],
        "count": len(SEED_DATA["lines"]),
    }


@app.get("/api/lines/{line_number}")
def get_line(line_number: str):
    """Return a specific line with all stops."""
    for l in SEED_DATA["lines"]:
        if str(l.get("number")) == line_number:
            stations_list = l.get("stations") or l.get("stops") or []
            stops = []
            # If stations is a list of IDs, look them up in seed stations
            if stations_list and isinstance(stations_list[0], (int, str)):
                for sid in l.get("stations", []):
                    for st in SEED_DATA.get("stations", []):
                        if st.get("id") == sid:
                            stops.append({
                                "name": st.get("name"),
                                "lat": st.get("lat"),
                                "lon": st.get("lon"),
                                "lines": st.get("lines", []),
                            })
                            break
            elif stations_list and isinstance(stations_list[0], dict):
                # stations is already a list of dicts (like 5D's format with lat/lon)
                for s in stations_list:
                    stops.append({
                        "name": s.get("name", s.get("station", "")),
                        "lat": s.get("lat", s.get("latitude")),
                        "lon": s.get("lon", s.get("longitude")),
                        "order": s.get("order"),
                        "schedule": s.get("schedule"),
                    })
            else:
                for s in l.get("stops", []):
                    stops.append({
                        "name": s.get("name"),
                        "lat": s.get("lat"),
                        "lon": s.get("lon"),
                        "order": s.get("order"),
                        "schedule": s.get("schedule"),
                        "stop_id": s.get("stop_id"),
                    })
            return {
                "line": l,
                "stops": stops,
                "count": len(stops),
            }
    return {"error": f"Line {line_number} not found"}


@app.get("/")
def index():
    return FileResponse(BASE / "frontend" / "index.html")


@app.get("/favicon.svg")
def favicon_svg():
    icon = BASE / "frontend" / "favicon.svg"
    if icon.exists():
        return FileResponse(icon, media_type="image/svg+xml")
    return JSONResponse({"error": "no favicon"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
